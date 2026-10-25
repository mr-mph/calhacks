# Soar-on live map (Convex)

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
npx convex dev                  # first run logs in and picks the project; keeps pushing convex/ on every save
pnpm dev                        # http://localhost:5173
```

Which deployments the page talks to is fixed at build time in `src/config.ts`: `pnpm dev` uses the Convex dev
deployment and links Markets to the market page's dev server (`market/web`, port 5174); `pnpm build` uses Convex
production and `https://overhead-market.vercel.app`. `VITE_CONVEX_URL` and `VITE_MARKET_URL` override either.
Typecheck and lint: `pnpm build`, `pnpm lint`.

## Data (web/convex/)

| Table | One row per | Written by |
|---|---|---|
| `observations` | processed frame (record from docs/architecture.md section 3) | `ingest:batch` |
| `frames` | uploaded JPEG in Convex file storage; only the newest 30 are kept, plus frames an alert points at | `ingest:batch` |
| `sites` | site map (zones and space polygons in reference-frame pixels) | `ingest:setSite` |
| `prices` | price point for a lot | every decision, or `ingest:batch` `prices` |
| `decisions` | pricing decision: inputs, action, price before/after, explanation | `ingest:batch` |
| `alerts` | drafted beach alert, status `needs_review`, `confirmed` or `dismissed`, plus its Jira send result and optional Grok audio (`audioId` in file storage, `voice`) | `ingest:batch`; status by `alerts:review`; `jira` by `jira:send` |
| `watchHours` | session and hour: frames watched and the most people in the water with a rip in view | `ingest:batch` |

Queries the page uses: `live:now` (frame, observation, site), `live:lots` (prices and decisions per lot),
`live:alerts`, `stats:lastDay` (the strip above Alerts: alerts drafted, confirmed and dismissed, median and slowest
seconds from frame to confirmation, people near a rip, frames watched, Jira incidents, over the 24 h ending at the
newest frame). They are split so a new frame every 2 s only re-runs `live:now` and the small `stats:lastDay`.
`watchHours` exists so the stats never scan `observations`, which would hit Convex's per-query read limit on a
multi-hour flight; frames ingested before it existed are not counted.

Ingest functions require the shared secret in Convex env var `INGEST_SECRET`. Dev and prod have different
secrets. To rotate one:

```bash
openssl rand -hex 24            # then update both places:
npx convex env set INGEST_SECRET <value>          # add --prod for production
# and "ingest_secret" (top level for dev, under "prod" for production) in ~/.config/balloon/convex.json (chmod 600)
```

## Patrol code

Anyone can read alerts. Confirming or dismissing one (`alerts:review`) needs the patrol code, Convex env var
`PATROL_CODE` (the same value on dev and prod). The page asks for it the first time someone taps Confirm or Dismiss
and remembers it in that phone's browser; a wrong code is forgotten and the page asks again. The station laptop
keeps a copy as `"patrol_code"` in `~/.config/balloon/convex.json`; share it with patrol members in person. To
rotate it:

```bash
openssl rand -hex 5
npx convex env set PATROL_CODE <value> && npx convex env set --prod PATROL_CODE <value>
# and "patrol_code" in ~/.config/balloon/convex.json
```

It is a shared passcode, not a login: anyone who has it can review alerts. Add Convex Auth before real patrol use.

## Alerts read aloud (Grok)

The station reads each alert aloud with xAI's Grok text-to-speech and uploads the MP3 with the alert
(`ground/STATION.md`, "Alert voice"). `live:alerts` returns its `audioUrl`. Each alert card with audio has a
Play alert button labelled "Voice by Grok". The "Read new alerts aloud" switch at the top of Alerts plays each new
alert's audio as it arrives, on that phone only, while the page is open (on either tab). It is off by default and
remembered in `localStorage` (`overhead-read-aloud`). Browsers block sound until someone taps, so the tap on the
switch is what allows it; if a browser still blocks it (for example after a reload), the page says so and asks for
the switch to be turned off and on again. `admin:purgeSession` deletes the audio files with the alerts.

## Confirmed alerts go to Jira

Confirming an alert schedules `jira:send`, a Convex action that POSTs it to the Balloon Patrol web trigger
(`atlassian/README.md`) with the alert's zone, counts, confidence and a public Convex storage URL of its frame. The
alert row keeps the result in `jira` (`sending`, `sent` with the issue key and the agent's reason, or `failed` with
the error), and the card shows it: "Sent to Jira: BPAT-3, Highest, assigned to ...". A failed or stalled send shows
the error and a Retry button (`alerts:retryJira`, patrol code required); retries are safe because the app ignores an
`alert_id` it already handled. Failed sends stay in "Recently reviewed" until they go through.

The action reads Convex env vars `FORGE_WEBTRIGGER_URL`, `FORGE_SECRET` and `FORGE_HEADER`, set on dev and prod from
`~/.config/balloon/forge.json` by piping each value in, so the secret never lands in shell history:

```bash
python3 -c 'import json,pathlib; print(json.loads((pathlib.Path.home()/".config/balloon/forge.json").read_text())["secret"], end="")' \
  | npx convex env set FORGE_SECRET            # add --prod for production; same for webtrigger_url and header
```

## Connecting the ground station

`ground/station.py` sends to Convex whenever `~/.config/balloon/convex.json` exists, to dev by default and to
production with `--prod` (see `ground/STATION.md`). The file:

```json
{"url": "https://<dev>.convex.cloud", "ingest_secret": "...", "patrol_code": "...",
 "prod": {"url": "https://<prod>.convex.cloud", "ingest_secret": "..."}}
```

`ground/convex_sink.py` can also be used on its own:

```python
from convex_sink import ConvexSink

sink = ConvexSink(env="prod")                               # "dev" (default) or "prod"
sink.set_site(site_json)                                    # once per tether spot (docs/architecture.md section 2)
sink.upload_frame(jpeg_bytes_or_path, session, t, (w, h), name=obs["frame"])  # name must equal the observation's "frame"
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

Remove a replay's rows (internal functions, CLI only; repeat until every count is 0):

```bash
npx convex run admin:purgeSession '{"session": "<session>"}'      # add --prod for production
npx convex run admin:purgeSite '{"site": "<site>"}'
```

## Deploy

Production: Convex `https://agreeable-penguin-576.convex.cloud`, page `https://overhead-live.vercel.app` (Vercel
project `overhead-live`).

```bash
cd web
npx convex deploy               # pushes convex/ to the production deployment
vercel deploy --prod            # builds with src/config.ts production targets (vercel.json: pnpm, dist/)
```

The app uses hash routes (`#/live`, `#/alerts`), so no rewrite rules are needed. Markets is the other app
(`market/web`, `https://overhead-market.vercel.app`); its Live and Alerts tabs link back here.
