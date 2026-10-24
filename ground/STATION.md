# Ground station

The laptop side of the balloon. It pulls stills from the Pi (or a recorded session), runs the detector, aligns
each frame to the site's reference frame, writes one observation record per frame, and runs the pricing, market
and beach-alert agents. Data shapes follow `docs/architecture.md`.

```
stills (Pi or session folder) -> infer.py (YOLO) -> align.py (ORB + RANSAC) -> observe.py -> sinks.py (JSONL)
                                                                                   |        convex_sink.py (live map)
                                                         agents/pricing.py, markets.py,     spacetime_sink.py (markets)
                                                         alerts.py
```

## Setup

```bash
cd ground
python3 -m venv .venv
.venv/bin/pip install -r requirements-station.txt   # detector stack + agents, one venv
```

The first run downloads `yolo11n.pt` (COCO). Point `BALLOON_WEIGHTS` at the VisDrone weights once they exist.

## Run

Replay a recorded session (from `./fetch.sh`), the demo fallback if we can't fly:

```bash
cd ground
.venv/bin/python station.py --replay ~/balloon-data/20261024-153000 --site sites/marina.json --agents
```

Live, against the Pi over the hotspot or USB-C, feeding the public map:

```bash
.venv/bin/python station.py --pi http://balloon.local:8080 --site sites/marina.json --agents --prod
```

Live mode polls `/api/status` for the current session, reads `/data/sessions/<session>/stills/index.csv` every
2 s, and downloads only stills it hasn't seen. It starts at the newest still instead of working through the backlog.

| Flag | What it does |
|---|---|
| `--site PATH` | Site JSON. Without it you still get frame-wide counts, but no zones, spaces or prices |
| `--agents` | Runs pricing, markets and beach alerts on each observation |
| `--every N` | Replay: process every Nth still |
| `--weights PATH` | YOLO weights (default `$BALLOON_WEIGHTS`, then `yolo11n.pt`) |
| `--market-every MIN` | Minutes between market proposals (default 30; the first comes after 10 min of history) |
| `--align-mode` | `similarity` (default, nadir camera) or `homography` (oblique views) |
| `--out DIR` | Output root (default `ground/out`) |
| `--realtime` | Replay: shift timestamps so the first still is now and play at the recorded pace. Markets need this, because Spacetime only takes current counts and future closes |
| `--loop` | Replay: start over at the end, forever (implies `--realtime`) |
| `--convex` / `--no-convex` | Send frames, counts, prices and alerts to the live map. On when `~/.config/balloon/convex.json` exists |
| `--prod` | Convex: the production deployment (the public map) instead of dev |
| `--spacetime` / `--no-spacetime` | Send counts, new markets and settlements to Spacetime. On when `~/.config/balloon/spacetime.json` exists |
| `--convex-config`, `--spacetime-config` | Other config files, for example a throwaway Spacetime database |

## Cloud

Both cloud sinks queue and return at once, so a slow network never stalls the detector. If either backend is
unreachable the station keeps running and logs a warning; the JSONL files are always complete.

**Convex (live map).** `~/.config/balloon/convex.json` (chmod 600): the top level is the dev deployment, `"prod"` the
production one, and `"patrol_code"` is the code patrol members type to confirm alerts.

```json
{"url": "https://<dev>.convex.cloud", "ingest_secret": "...", "patrol_code": "...",
 "prod": {"url": "https://<prod>.convex.cloud", "ingest_secret": "..."}}
```

The station sends the site map once, then every frame (shrunk to 1280 px) with its observation, every pricing
decision and every beach alert. Market decisions go to Spacetime only.

**Spacetime (markets).** `~/.config/balloon/spacetime.json` (chmod 600, see `market/README.md`). Counts post as
`post_observation` per zone and metric, only when the value changes or every 10 s: `car_count`, `person_count`,
and `occupancy_pct` (0 to 100) per zone, plus `car_count` and `person_count` for the zone `whole-view`. The market
agent has its own oracle identity, claimed with `oracle_secret` on first run and saved as `agent_token`. Each
accepted proposal becomes `create_market` with the agent's one-sentence rationale as the last argument. At close
plus 60 s the engine in `agents/markets.py` settles it (median of frames within 60 s, confidence at least 0.5, at
least 3 frames) and the sink calls `settle` with that value and the explanation, or `void_market` when there are too
few good frames.

## Demo replay

When the balloon can't fly, replay a recorded session through everything, looping, onto the public map and markets:

```bash
ground/demo.sh ~/balloon-data/20261024-153000              # site defaults to ground/sites/<session name>.json
ground/demo.sh <session-dir> sites/marina.json --no-spacetime
```

It runs `station.py --replay <dir> --site <site> --agents --loop --prod` with the VisDrone weights from
`ground/runs/visdrone/weights/best.pt` when they exist. The first market is proposed after 10 minutes of replay
and settles after its close, so start it at least 45 minutes before you need a settled market on screen.

Remove a replay's rows from the map afterwards (the market database has no delete; use a throwaway database
with `--spacetime-config` for rehearsals):

```bash
cd web && npx convex run --prod admin:purgeSession '{"session": "<session name>"}'   # repeat until all counts are 0
npx convex run --prod admin:purgeSite '{"site": "<site name>"}'
```

**Stand-in session.** Until we have a flight, `sites/visdrone-standin-0000356.json` maps a stand-in session: 10 real
frames from the public VisDrone2019 val set, sequence 0000356 (a near-hovering view of a crossing with a small lot),
which all align to one reference. To rebuild it, copy these val images in order into
`ground/out/sessions/visdrone-standin-0000356/stills/` as `1792900000.000.jpg`, `1792900002.000.jpg`, and so on
(2 s apart), and list them in `stills/index.csv` with `t_unix` set and the telemetry columns blank:

```
0000356_02353_d_0000641  0000356_02745_d_0000643  0000356_02941_d_0000644  0000356_03333_d_0000646  0000356_03529_d_0000647
0000356_03725_d_0000648  0000356_03921_d_0000649  0000356_04117_d_0000650  0000356_04313_d_0000651  0000356_04705_d_0000653
```

It is not balloon data: there is no telemetry, and the street is in the VisDrone set, not San Francisco.

## Output

`ground/out/<session>/`:

| File | One line per |
|---|---|
| `observations.jsonl` | processed frame, exactly the record in architecture.md section 3 |
| `decisions.jsonl` | every pricing change; a pricing hold when its category (frame or policy) changes, else at most one per 5 minutes per lot; market proposal (accepted or rejected, with the reason), market settlement |
| `alerts.jsonl` | beach alert, always `"status": "needs_review"` until a person confirms it |

`audio/alert-<t>.mp3` holds each alert read aloud by Grok. `ground/out/spend.json` holds the Claude and Grok spend
per session (see the guard below).

## Drawing a site

Open `sites/editor.html` in a browser (it works offline, no build step). Load a reference still, then:

- **Z** draws a zone: pick its kind (lot, beach, water, crossing), click the corners, press Enter.
- **S** draws one parking space inside the lot chosen under "Spaces belong to".
- **G** draws a grid: click the four corners of a block of spaces in order (top-left, top-right, bottom-right,
  bottom-left) and it splits them into rows x columns spaces named A01, A02, and so on.
- **V** selects; edit the id, kind or capacity in the side panel; Delete removes it.
- Cmd+S (or the button) downloads `<site>.json`.

Save the JSON in `ground/sites/` and put the reference image next to it, or set `reference_frame` to a path relative
to the session folder (`stills/1792880000.000.jpg`). The schema is `sites/site.schema.json`.

## Observation confidence

`confidence` is the product of three factors, so any one problem pulls a frame under 0.5:

| Factor | Value |
|---|---|
| Alignment | 0.7 to 1.0 by inlier ratio when aligned, 0.4 when alignment fails, 1.0 when no site is loaded |
| Tilt | 1.0 at 0 degrees falling to 0.8 at 15 degrees, 0.4 above 15, 0.9 when unknown |
| Count stability | 1.0 when car and person counts match the median of the last 5 frames, down to 0.5 for big jumps |

When a frame doesn't align, its `zones` and `spaces` are empty: we don't guess where the polygons are.

## Agents

Claude writes words; the engines set every number.

- **Pricing** (`agents/pricing.py`). Per lot zone: base price at or below 60% occupancy, rising linearly to the
  cap at 100%. At most one change per 5 minutes, at most 25% per step, always within floor and ceiling, and a hold
  when the frame didn't align or its confidence is below 0.5. Each decision records its inputs and policy.
  Claude writes a one-paragraph explanation of each change.
- **Markets** (`agents/markets.py`). Binary markets on counts at a moment (cars or occupancy in a lot, people in a
  zone, or counts in the whole view). Settlement is the median of observations within 60 s of close with
  confidence at least 0.5; fewer than 3 such frames voids the market and returns stakes. LMSR helpers
  (`lmsr_cost`, `lmsr_prices`, `lmsr_buy`, `lmsr_opening_q`) are pure functions for the Spacetime module to
  mirror. Claude proposes markets from the history; every proposal goes through guardrails (known zone, field
  that fits the zone kind, threshold within capacity and observed range, close 10 to 360 minutes out, opening
  probability 0.05 to 0.95, no duplicates), and the question text is generated from the validated fields.
  Claude also explains each settlement.
- **Beach alerts** (`agents/alerts.py`). Fires on a rip candidate or people in a water zone, at most once every
  2 minutes. Claude gets the frame (downscaled to 1024 px), the detections and counts, and returns a short alert
  plus an uncertainty line. It counts people and never describes or identifies anyone. Low-confidence frames
  still produce an alert, marked as a lead rather than a finding.
- **Alert voice** (`agents/voice.py`). Each alert, once written, is read aloud by Grok: one call to xAI's
  text-to-speech endpoint (`POST https://api.x.ai/v1/tts`, voice `rex`, MP3 24 kHz 64 kbps) with "Beach alert."
  plus the alert and its uncertainty line. The MP3 lands in `out/<session>/audio/`, the alert record points at it
  (`"audio": {"file", "voice", "bytes"}`), and the Convex sink uploads it with the alert so the live map can play
  it. xAI charges $15 per million characters, about $0.003 to $0.005 per alert. Without `XAI_API_KEY`, over the
  cap, or on an xAI error, the alert goes out without audio. The call blocks the station for 1 to 3 s, at most
  once every 2 minutes.

Without a key every agent runs in engine-only mode: same numbers, template wording, and `explained_by` or
`written_by` says `engine`.

## Claude budget and the spend guard

The org has a small monthly budget, so:

- Claude is called only on events (a price change, a settlement, a proposal round, an alert), never per frame.
- Text work (explanations, proposals) defaults to `claude-haiku-5-5`; the vision alert to `claude-sonnet-5-5`.
- Before each call the guard estimates the worst-case cost (input tokens plus `max_tokens`). If that would push
  the session past the cap, the call is refused, logged, and the agent falls back to engine wording.
- After each call the actual cost from the response's token usage is added to `ground/out/spend.json`, per
  session and per purpose. Restarting the station keeps the running total.
- Grok alert audio counts against the same cap, as purpose `voice` (characters times xAI's published price,
  checked before the call).

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Claude key. If unset, read from the file in `BALLOON_ENV_FILE` |
| `BALLOON_ENV_FILE` | the main checkout's env file | dotenv file to read the key from (never printed or logged) |
| `BALLOON_TEXT_MODEL` | `claude-haiku-5-5` | explanations and market proposals |
| `BALLOON_VISION_MODEL` | `claude-sonnet-5-5` | beach alerts |
| `BALLOON_SPEND_CAP_USD` | `10` | Claude plus Grok voice spend cap per session |
| `XAI_API_KEY` | none | xAI key for alert audio. If unset, read from the file in `BALLOON_ENV_FILE` |
| `BALLOON_VOICE_ID` | `rex` | Grok voice (`GET https://api.x.ai/v1/tts/voices` lists them) |
| `BALLOON_WEIGHTS` | `yolo11n.pt` | detector weights |
| `BALLOON_MODEL_NAME` | weights file stem | `model` field in observations, e.g. `yolo11n-visdrone-v1` |
| `BALLOON_IMGSZ` | `1280` | detector input size |

## Tests

```bash
cd ground
.venv/bin/python -m pytest tests -q
```

Image tests use real drone frames from the public VisDrone2019 val set, downloaded once into the pytest cache.
`tests/test_live_claude.py` makes one real call per agent (three in total, capped at $0.50) and skips without a key.
`tests/test_live_voice.py` makes one real Grok text-to-speech call (about $0.003), writes `out/voice-smoke.mp3`
and checks it parses as MP3 frames; it skips without `XAI_API_KEY`.

## Not built yet

Markets on flows over a period ("people crossing between 4 and 5 PM") need a crossing counter; today's markets settle on counts at one
moment.

## Satellite comparison

`satellite.py` fetches free imagery from Microsoft Planetary Computer (anonymous, no key) and sets it beside a balloon frame.

```bash
.venv/bin/python satellite.py fetch --lat 37.7598 --lon -122.5107 --radius-m 150 --out out/satellite/ocean-beach
.venv/bin/python satellite.py compare --frame frame.jpg --obs obs.json --summary out/satellite/ocean-beach/summary.json --out out/compare
```

`fetch` takes the newest Sentinel-2 L2A scene under 20% cloud (10 m, `visual` asset) and the newest NAIP scene
(about 0.6 m, US only), crops both to the square around the point, and writes `sentinel2.png`, `naip.png` and
`summary.json` (source, acquired_at, age_days, gsd_m, cloud_cover, bbox, pixel_size_of_a_car_px, png_path). Cloud
cover is the whole scene's, not the crop's. NAIP is a yearly survey, so its age is often years.

`compare` takes a frame and an observation record (`alt_m`, `counts`, `t`) and writes `compare.png` (balloon and
satellite panels, nearest-neighbour upscaled) and `compare.json`: balloon cm/px from altitude and `--hfov-deg`
(default 70), data age in seconds against the satellite's in days, and whether a 4.5 m car spans at least
`--min-car-px` pixels (default 8, an assumption written into the JSON). The crops are not registered to the frame.
