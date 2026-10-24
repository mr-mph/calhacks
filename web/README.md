# Overhead live map (Convex)

The phone page for drivers and beach patrol: the newest aerial frame with free and taken spaces drawn on it, the
counts, lot prices with their decision log, and beach alerts that a patrol member confirms or dismisses. The laptop
ground station writes to Convex; every open page updates live through Convex queries.

```
ground station (laptop) --ground/convex_sink.py--> Convex (web/convex/) --useQuery--> this app (web/src/)
```

## Setup

Needs Node 22+ and pnpm. The Convex dev deployment already exists (project `balloon-ground`).

```bash
cd web
pnpm install                    # esbuild is the only package allowed to run a build script
npx convex dev                  # first run logs in / picks the project and writes .env.local (VITE_CONVEX_URL)
pnpm dev                        # http://localhost:5173
```

`npx convex dev` keeps running and pushes `convex/` on every save. Typecheck and lint: `pnpm build`, `pnpm lint`.

## Data (web/convex/)

| Table | One row per | Written by |
|---|---|---|
| `observations` | processed frame (record from docs/architecture.md section 3) | `ingest:batch` |
| `frames` | uploaded JPEG in Convex file storage; only the newest 30 are kept, plus frames an alert points at | `ingest:batch` |
| `sites` | site map (zones and space polygons in reference-frame pixels) | `ingest:setSite` |
| `prices` | price point for a lot | every decision, or `ingest:batch` `prices` |
| `decisions` | pricing decision: inputs, action, price before/after, explanation | `ingest:batch` |
| `alerts` | drafted beach alert, status `needs_review`, `confirmed` or `dismissed` | `ingest:batch`; status by `alerts:review` |

Queries the page uses: `live:now` (frame, observation, site), `live:lots` (prices and decisions per lot),
`live:alerts`. They are split so a new frame every 2 s only re-runs `live:now`.

Ingest functions require the shared secret in Convex env var `INGEST_SECRET`. To rotate it:

```bash
openssl rand -hex 24            # then update both places:
npx convex env set INGEST_SECRET <value>
# and "ingest_secret" in ~/.config/balloon/convex.json on the station laptop (chmod 600)
```

`alerts:review` has no login: anyone with the page can confirm or dismiss an alert. That's fine for the demo; add
Convex Auth before real patrol use.

## Connecting the ground station

The station reads `~/.config/balloon/convex.json`:

```json
{"url": "https://<deployment>.convex.cloud", "ingest_secret": "<same value as INGEST_SECRET>"}
```

```bash
ground/.venv/bin/pip install convex==0.8.1
```

```python
from convex_sink import ConvexSink

sink = ConvexSink()
sink.set_site(site_json)                                    # once per tether spot (docs/architecture.md section 2)
sink.upload_frame(path, session, t, (w, h), name=obs["frame"])  # name must equal the observation's "frame"
sink.write_observations([obs])
sink.write_decision({"t": t, "zone": "lot-a", "action": "raise", "price_before": 3.0, "price_after": 3.75,
                     "inputs": {"occupancy": 0.75, "confidence": 0.9}, "explanation": "..."})
sink.write_alert({"t": t, "text": "...", "uncertainty": "...", "severity": "warning", "frame": obs["frame"]})
sink.close()
```

Every method only queues and returns at once. A background thread sends one batched mutation per 2 s (frame +
observations + decisions + alerts), so the station costs about 2 Convex calls per frame: 3,600 an hour, well inside
the free tier's 1M calls a month. If Convex is unreachable, the sink keeps up to 500 queued items and only the newest
frame, and retries with backoff. Frames wider than 1280 px are shrunk before upload when OpenCV is installed, which
keeps file bandwidth down (every open phone downloads each frame).

End-to-end check with real VisDrone frames (detections from `ground/detect.py`, spaces from `ground/parking.py`):
`python web/scripts/e2e_visdrone_replay.py <frames dir> detections.jsonl parking.jsonl`. Its pricing decisions and
its one alert are labelled test data.

## Deploy

```bash
cd web
npx convex deploy               # pushes convex/ to the production deployment
npx convex env set --prod INGEST_SECRET <value>
```

Then point the station's `convex.json` `url` at the production URL. The frontend is a static site:

```bash
VITE_CONVEX_URL=https://<prod-deployment>.convex.cloud pnpm build    # outputs dist/
```

Host `dist/` on any static file host. The app uses hash routes
(`#/live`, `#/markets`, `#/alerts`), so no rewrite rules are needed. Set `VITE_MARKET_URL` at build time to link the
Markets tab to the market page.
