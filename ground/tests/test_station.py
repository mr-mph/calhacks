import json
import shutil

import station
from station import parse_index, replay_stills

INDEX_HEADER = "file,t_unix,altitude_m,pitch_deg,roll_deg,tilt_deg\n"


def make_session(tmp_path, real_images):
    session = tmp_path / "20261024-153000"
    stills = session / "stills"
    stills.mkdir(parents=True)
    rows = []
    for i, key in enumerate(("street_a", "street_b", "street_a")):
        name = f"{1792880000 + 2 * i:.3f}.jpg"
        shutil.copy(real_images[key], stills / name)
        rows.append(f"{name},{1792880000 + 2 * i:.3f},92.4,1.0,2.0,{3.0 + i}\n")
    (stills / "index.csv").write_text(INDEX_HEADER + "".join(rows))
    return session


def test_parse_index_skips_blank_rows():
    rows = parse_index(INDEX_HEADER + "a.jpg,1.0,,,,\n,,,,,\n")
    assert [r["file"] for r in rows] == ["a.jpg"]


def test_replay_reads_telemetry(tmp_path, real_images):
    stills = list(replay_stills(make_session(tmp_path, real_images)))
    assert [s.tilt_deg for s in stills] == [3.0, 4.0, 5.0]
    assert stills[0].alt_m == 92.4 and stills[0].session == "20261024-153000"


def test_replay_end_to_end(tmp_path, real_images, detector, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("BALLOON_ENV_FILE", str(tmp_path / "missing"))
    monkeypatch.setenv("BALLOON_WEIGHTS", detector.weights)
    session = make_session(tmp_path, real_images)
    site = {"site": "street", "reference_frame": str(real_images["street_a"]),
            "zones": [{"id": "lot-a", "kind": "lot", "capacity": 20,
                       "polygon": [[0, 380], [1360, 380], [1360, 765], [0, 765]]}]}
    site_path = tmp_path / "street.json"
    site_path.write_text(json.dumps(site))
    out = tmp_path / "out"
    station.main(["--replay", str(session), "--site", str(site_path), "--out", str(out), "--agents"])
    lines = (out / session.name / "observations.jsonl").read_text().splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 3
    assert all(r["aligned"] for r in records)
    assert records[0]["frame"] == "stills/1792880000.000.jpg"
    assert "occupancy" in records[0]["zones"]["lot-a"]
    decisions = [json.loads(line) for line in (out / session.name / "decisions.jsonl").read_text().splitlines()]
    assert decisions and all(d["agent"] == "pricing" for d in decisions)
