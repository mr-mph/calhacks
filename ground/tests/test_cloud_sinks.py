import json
import stat

import pytest

import convex_sink
import spacetime_sink
import station
from agents.markets import MarketAgent, settle, validate_proposal
from spacetime_sink import SpacetimeClient, SpacetimeSink, Throttle, ensure_agent_token, readings

HOST, DB = "https://spacetime.test", "overhead-market"
LOT = {"id": "lot-a", "kind": "lot", "capacity": 48, "polygon": [[0, 0], [10, 0], [10, 10]]}


class FakeResponse:
    def __init__(self, status_code: int = 200, body=None, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise spacetime_sink.requests.HTTPError(str(self.status_code))


class FakeSpacetime:
    """The HTTP surface of the market module: identity, reducer calls, and SELECT on the market table."""

    def __init__(self, reject: str | None = None):
        self.calls: list[tuple[str, str, list]] = []
        self.markets: list[dict] = []
        self.reject = reject

    def post(self, url, data=None, headers=None, timeout=None):
        if url.endswith("/v1/identity"):
            return FakeResponse(body={"identity": "abc", "token": f"token-{len(self.calls)}"})
        if url.endswith("/sql"):
            names = ["id", "question", "zone", "metric", "threshold", "status"]
            rows = [[m[n] for n in names] for m in self.markets]
            return FakeResponse(body=[{"schema": {"elements": [{"name": {"some": n}} for n in names]}, "rows": rows}])
        reducer = url.rsplit("/", 1)[1]
        token = headers["Authorization"].removeprefix("Bearer ")
        args = json.loads(data)
        self.calls.append((reducer, token, args))
        if reducer == self.reject:
            return FakeResponse(530, text="only an oracle can do this")
        if reducer == "create_market":
            question, zone, metric, _, threshold = args[:5]
            self.markets.append({"id": len(self.markets) + 1, "question": question, "zone": zone, "metric": metric,
                                 "threshold": threshold, "status": "open"})
        return FakeResponse()

    def reducers(self, name: str) -> list[list]:
        return [args for reducer, _, args in self.calls if reducer == name]


def make_sink(http: FakeSpacetime, clock=lambda: 0.0) -> SpacetimeSink:
    return SpacetimeSink(SpacetimeClient(HOST, DB, "station-token", http), SpacetimeClient(HOST, DB, "agent-token", http),
                         Throttle(10.0, clock))


def observation(t: float, cars: int, occupancy: float, confidence: float = 0.9) -> dict:
    return {"t": t, "session": "s", "frame": f"stills/{t:.0f}.jpg", "confidence": confidence, "aligned": True,
            "counts": {"car": cars, "person": 2}, "zones": {"lot-a": {"car": cars, "occupancy": occupancy}}}


def test_readings_cover_zone_fields_and_whole_view():
    assert readings(observation(1.0, 37, 0.77)) == [
        ("lot-a", "car_count", 37), ("lot-a", "occupancy_pct", 77.0),
        ("whole-view", "car_count", 37.0), ("whole-view", "person_count", 2.0),
    ]


def test_throttle_posts_on_change_or_every_ten_seconds():
    now = [0.0]
    throttle = Throttle(10.0, lambda: now[0])
    assert throttle.due("lot-a", "car_count", 37)
    now[0] = 5.0
    assert not throttle.due("lot-a", "car_count", 37)
    assert throttle.due("lot-a", "car_count", 38)
    now[0] = 15.1
    assert throttle.due("lot-a", "car_count", 38)


def test_observations_post_once_per_change_with_station_identity():
    http = FakeSpacetime()
    sink = make_sink(http)
    sink.write("observations", observation(100.0, 37, 0.77))
    sink.write("observations", observation(102.0, 37, 0.77))
    sink.write("observations", observation(104.0, 38, 0.79))
    sink.close()
    posts = [(token, args) for reducer, token, args in http.calls if reducer == "post_observation"]
    assert {token for token, _ in posts} == {"station-token"}
    lot_cars = [args for _, args in posts if args[1:3] == ["lot-a", "car_count"]]
    assert lot_cars == [[100.0, "lot-a", "car_count", 37, 0.9, "stills/100.jpg"],
                        [104.0, "lot-a", "car_count", 38, 0.9, "stills/104.jpg"]]


def proposal_record(field: str = "car", threshold: float = 40, rationale: str = "Lot A held 35 to 42 cars.") -> dict:
    zones = {"lot-a": LOT}
    p = {"zone": "lot-a", "field": field, "comparator": ">=", "threshold": threshold, "close_in_minutes": 30,
         "open_prob": 0.5, "rationale": rationale}
    market, problem = validate_proposal(p, zones, 45, 1_000.0, [])
    assert problem is None
    return {"agent": "markets", "kind": "proposal", "accepted": True, "market": market}


def test_accepted_proposal_creates_market_with_rationale_last_and_agent_identity():
    http = FakeSpacetime()
    sink = make_sink(http)
    record = proposal_record()
    sink.write("decisions", record)
    sink.write("decisions", {**record, "accepted": False, "market": None})
    sink.write("decisions", {"agent": "pricing", "action": "raise"})
    sink.close()
    creates = [(token, args) for reducer, token, args in http.calls if reducer == "create_market"]
    assert len(creates) == 1
    token, args = creates[0]
    market = record["market"]
    assert token == "agent-token"
    assert args == [market["question"], "lot-a", "car_count", ">=", 40, market["close_t"], 100,
                    "Lot A held 35 to 42 cars."]
    assert sink.market_ids[market["id"]] == (1, 1.0)


def test_settlement_uses_engine_median_and_scales_occupancy():
    http = FakeSpacetime()
    sink = make_sink(http)
    record = proposal_record(field="occupancy", threshold=0.75, rationale="")
    market = record["market"]
    frames = [{"t": market["close_t"] + d, "confidence": 0.9, "zones": {"lot-a": {"occupancy": occ}}}
              for d, occ in ((-30, 0.70), (0, 0.80), (20, 0.85), (40, 0.2))]
    frames.append({"t": market["close_t"] + 10, "confidence": 0.3, "zones": {"lot-a": {"occupancy": 0.1}}})
    settlement = {**settle(market, frames), "explanation": "Median of 4 good frames was 75% full."}
    sink.write("decisions", record)
    sink.write("decisions", settlement)
    sink.close()
    create = http.reducers("create_market")[0]
    assert create[2:5] == ["occupancy_pct", ">=", 75.0]
    assert create[7] == spacetime_sink.DEFAULT_RATIONALE
    assert http.reducers("settle") == [[1, 75.0, "Median of 4 good frames was 75% full."]]
    assert sink.market_ids == {}


def test_void_settlement_refunds_through_void_market():
    http = FakeSpacetime()
    sink = make_sink(http)
    record = proposal_record()
    void = settle(record["market"], [])
    assert void["status"] == "void"
    sink.write("decisions", record)
    sink.write("decisions", void)
    sink.close()
    assert http.reducers("void_market") == [[1, void["reason"]]]
    assert http.reducers("settle") == []


def test_rejected_calls_are_logged_not_raised(caplog):
    http = FakeSpacetime(reject="post_observation")
    sink = make_sink(http)
    sink.write("observations", observation(1.0, 3, 0.1))
    sink.close()
    assert sink.sent["failed"] == 4 and sink.sent["observations"] == 0
    assert "only an oracle can do this" in caplog.text


def test_agent_identity_is_claimed_once_and_saved_privately(tmp_path):
    path = tmp_path / "spacetime.json"
    cfg = {"host": HOST, "database": DB, "station_token": "station-token", "oracle_secret": "s" * 24}
    path.write_text(json.dumps(cfg))
    http = FakeSpacetime()
    client = SpacetimeClient(HOST, DB, "station-token", http)
    token = ensure_agent_token(dict(cfg), path, client)
    assert http.reducers("claim_oracle") == [["s" * 24]]
    assert json.loads(path.read_text())["agent_token"] == token
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert ensure_agent_token(json.loads(path.read_text()), path, client) == token
    assert len(http.reducers("claim_oracle")) == 1


class FakeConvexClient:
    def __init__(self, url: str):
        self.url = url
        self.mutations: list[tuple[str, dict]] = []

    def mutation(self, name: str, args: dict):
        self.mutations.append((name, args))
        return "https://upload.test" if name == "ingest:generateUploadUrl" else None


def write_convex_config(tmp_path):
    path = tmp_path / "convex.json"
    path.write_text(json.dumps({"url": "https://dev.convex.cloud", "ingest_secret": "dev-secret",
                                "prod": {"url": "https://prod.convex.cloud", "ingest_secret": "prod-secret"}}))
    return path


def test_convex_config_picks_dev_or_prod(tmp_path):
    path = write_convex_config(tmp_path)
    assert convex_sink.load_config(path)["url"] == "https://dev.convex.cloud"
    assert convex_sink.load_config(path, "prod")["ingest_secret"] == "prod-secret"
    path.write_text(json.dumps({"url": "https://dev.convex.cloud", "ingest_secret": "x"}))
    with pytest.raises(ValueError, match="prod"):
        convex_sink.load_config(path, "prod")


def pricing_decision() -> dict:
    return {"agent": "pricing", "t": 5.0, "session": "s", "zone": "lot-a", "frame": "stills/5.jpg", "action": "raise",
            "old_price": 3.0, "new_price": 3.75, "target_price": 4.5, "code": "raise", "reason": "raise: 75%",
            "inputs": {"occupancy": 0.75, "confidence": 0.9, "aligned": True, "cars": 36, "last_change_t": None},
            "policy": {"base": 3.0}, "explanation": "Lot A filled to 75%.", "explained_by": "claude-haiku-5-5"}


def test_station_records_map_to_convex_tables():
    assert convex_sink.convex_decision(pricing_decision()) == {
        "t": 5.0, "zone": "lot-a", "action": "raise", "price_before": 3.0, "price_after": 3.75,
        "inputs": {"occupancy": 0.75, "confidence": 0.9, "aligned": True, "cars": 36.0},
        "outputs": {"target_price": 4.5, "code": "raise"}, "explanation": "Lot A filled to 75%.",
        "model": "claude-haiku-5-5"}
    hold = {**pricing_decision(), "action": "hold", "new_price": 3.0, "explanation": None, "explained_by": None}
    assert convex_sink.convex_decision(hold)["explanation"] == "raise: 75%"
    assert convex_sink.convex_decision({"agent": "markets", "kind": "proposal"}) is None
    alert = {"t": 9.0, "session": "s", "frame": "stills/9.jpg", "alert": "Rip forming north of the stairs.",
             "uncertainty": "Moderate.", "trigger": {"people_near_rip": 2}, "low_confidence": False,
             "written_by": "claude-sonnet-5-5"}
    assert convex_sink.convex_alert(alert)["severity"] == "critical"
    assert convex_sink.convex_alert({**alert, "low_confidence": True})["severity"] == "info"
    jira_ready = convex_sink.convex_alert({**alert, "zone": "surf", "confidence": 0.8, "counts": {"person": 7},
                                           "trigger": {"people_near_rip": 2, "people_in_water_zone": 3}})
    assert jira_ready["zone"] == "surf" and jira_ready["confidence"] == 0.8
    assert jira_ready["counts"] == {"person_water": 3, "person_beach": 4}
    site = {"site": "marina", "reference_frame": "ref.jpg", "zones": [LOT],
            "spaces": [{"id": "A01", "zone": "lot-a", "polygon": [[0, 0], [1, 0], [1, 1]]}]}
    shaped = convex_sink.convex_site(site, (1920, 1080))
    assert shaped["image_size"] == [1920.0, 1080.0] and "name" not in shaped["zones"][0]


def test_convex_sink_batches_frame_bytes_and_records(tmp_path, monkeypatch, real_images):
    monkeypatch.setattr(convex_sink, "ConvexClient", FakeConvexClient)
    monkeypatch.setattr(convex_sink.requests, "post",
                        lambda url, data, headers, timeout: FakeResponse(body={"storageId": "storage-1"}))
    sink = convex_sink.ConvexSink(write_convex_config(tmp_path), flush_interval_s=0.05, env="prod")
    sink.upload_frame(real_images["street_a"].read_bytes(), "s", 5.0, (1360, 765), name="stills/5.jpg")
    sink.write("observations", observation(5.0, 36, 0.75))
    sink.write("decisions", pricing_decision())
    sink.write("decisions", {"agent": "markets", "kind": "proposal"})
    assert sink.flush(10)
    sink.close()
    client = sink._client
    assert client.url == "https://prod.convex.cloud"
    batches = [args for name, args in client.mutations if name == "ingest:batch"]
    sent = {k: sum(len(b.get(k, [])) for b in batches) for k in ("observations", "decisions")}
    assert sent == {"observations": 1, "decisions": 1}
    assert all(b["secret"] == "prod-secret" for b in batches)
    frame = next(b["frame"] for b in batches if "frame" in b)
    assert frame["name"] == "stills/5.jpg" and frame["storageId"] == "storage-1"


def test_paced_replay_rebases_to_now_and_loops(tmp_path, real_images):
    from test_station import make_session

    session = make_session(tmp_path, real_images)
    now, slept = [5_000.0], []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    stills = station.paced_replay(session, loop=True, clock=lambda: now[0], sleep=sleep)
    times = [next(stills).t for _ in range(4)]
    assert times[:3] == [5_000.0, 5_002.0, 5_004.0]
    assert times[3] == 5_004.0 + station.LOOP_GAP_S
    assert sum(slept) == pytest.approx(4.0 + station.LOOP_GAP_S)


def test_cloud_flags_default_to_config_presence(tmp_path):
    present = write_convex_config(tmp_path)
    args = station.parse_args(["--replay", "x", "--convex-config", str(present),
                               "--spacetime-config", str(tmp_path / "missing.json")])
    assert args.convex and not args.spacetime
    args = station.parse_args(["--replay", "x", "--no-convex", "--convex-config", str(present)])
    assert not args.convex


def test_engine_market_agent_records_flow_into_spacetime():
    http = FakeSpacetime()
    sink = make_sink(http)
    agent = MarketAgent(None, {"zones": [LOT]})
    history = [observation(1_000.0 + 2 * i, 36 + i % 3, 0.75) for i in range(30)]
    for record in agent.propose(history, 1_060.0):
        sink.write("decisions", record)
    close = agent.open[0]["close_t"]
    closing = [observation(close + d, 37, 0.77) for d in (-20, 0, 20, 61)]
    for record in agent.settle_due(closing, close + 61):
        sink.write("decisions", record)
    sink.close()
    assert len(http.reducers("create_market")) == 1
    assert http.reducers("settle")[0][:2] == [1, 37]
