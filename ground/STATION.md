# Ground station

The laptop side of the balloon. It pulls stills from the Pi (or a recorded session), runs the detector, aligns
each frame to the site's reference frame, writes one observation record per frame, and runs the pricing, market
and beach-alert agents. Data shapes follow `docs/architecture.md`.

```
stills (Pi or session folder) -> infer.py (YOLO) -> align.py (ORB + RANSAC) -> observe.py -> sinks.py
                                                                                   |
                                                         agents/pricing.py, markets.py, alerts.py
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

Live, against the Pi over the hotspot or USB-C:

```bash
.venv/bin/python station.py --pi http://balloon.local:8080 --site sites/marina.json --agents
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

## Output

`ground/out/<session>/`:

| File | One line per |
|---|---|
| `observations.jsonl` | processed frame, exactly the record in architecture.md section 3 |
| `decisions.jsonl` | pricing change or new hold reason, market proposal (accepted or rejected, with the reason), market settlement |
| `alerts.jsonl` | beach alert, always `"status": "needs_review"` until a person confirms it |

`ground/out/spend.json` holds the Claude spend per session (see the guard below).

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

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Claude key. If unset, read from the file in `BALLOON_ENV_FILE` |
| `BALLOON_ENV_FILE` | the main checkout's env file | dotenv file to read the key from (never printed or logged) |
| `BALLOON_TEXT_MODEL` | `claude-haiku-5-5` | explanations and market proposals |
| `BALLOON_VISION_MODEL` | `claude-sonnet-5-5` | beach alerts |
| `BALLOON_SPEND_CAP_USD` | `10` | Claude spend cap per session |
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

## Not built yet

`ConvexSink` and `SpacetimeSink` in `sinks.py` are stubs that raise `NotImplementedError`. Markets on flows over
a period ("people crossing between 4 and 5 PM") need a crossing counter; today's markets settle on counts at one
moment.
