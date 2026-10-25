# Project status

As of **Saturday Oct 24, 5:31 PM**. Devpost closes at **9:00 AM Sunday**. Update this file when something changes.

## Live now

| What | Where | State |
|---|---|---|
| Live map | https://overhead-live.vercel.app | Aerial frame with parking spaces, counts, lot prices with the "why" log, beach alerts with a patrol passcode, one-tap Jira hand-off, Grok reads alerts aloud. Convex prod: `agreeable-penguin-576` |
| Prediction markets | https://overhead-market.vercel.app | Kalshi-style markets on Spacetime maincloud (`overhead-market`). Money provably balances. Markets open once the balloon is counting |
| Jira "Balloon Patrol" | https://one-atlas-dqcx.atlassian.net | Forge app in Jira and Confluence: creates incidents, merges duplicates, queues low-confidence frames, flags injection attempts. 4-alert smoke test passes |

## Models

| Model | Data | Result |
|---|---|---|
| Cars and people (YOLO11n) | VisDrone2019-DET, 50 epochs | Done. mAP50 car 0.72, pedestrian 0.31 (`ground/README.md`) |
| Rip currents (YOLO11n-OBB) | RipAID, 2 beach cameras held out | Done. mAP50 0.32 on unseen cameras (precision 0.49, recall 0.27); the station runs it automatically |
| Our own frames | Balloon flight | After the flight: auto-label, fix about 200 by hand, retrain |

## Code

- Everything is on `main`. Ground station and agents: 117 tests pass (`cd ground && .venv/bin/python -m pytest -q tests`).
- Satellite comparison (`ground/satellite.py`): free satellite imagery is 9 days old at 10 m per pixel, or 4 years old
  at 0.6 m; the balloon sees about 7 cm per pixel every 2 s.
- Docs: `CONTEXT.md` (plan), `docs/devpost.md` (submission draft), `docs/tracks.md` (every track's rules),
  `docs/design.md` (design system), `docs/architecture.md` (data flow), `docs/demo.md` (Sunday runbook and
  pitch).

## Tracks

| Track | What we have |
|---|---|
| Cal Hacks: Overall, Hardware, People-First, Planet-First, Technical | Everything, judged automatically. **Needs the real flight** |
| Anthropic: Claude for Public Benefit | Beach alerts by Claude, conversations with beachgoers and swimmers recorded, a person confirms every alert |
| Hyphenate | Surge-pricing and market agents with guardrails and decision logs. Their booth held office hours Saturday evening |
| Convex | The live map, plus confirmed alerts flowing into Jira |
| Spacetime | The whole prediction market |
| SpaceXAI | Satellite comparison and Grok voice. **Cursor usage still needed** |
| Atlassian | Balloon Patrol app, deployed |

## Blockers and to-dos

| # | What | Owner |
|---|---|---|
| 1 | **Fly the Pi and record a session.** Biggest gap: without it the demo runs on stand-in aerial footage | SF team |
| 2 | **Create the Devpost project tonight**: name "Overhead", add all 4 teammates, tick Anthropic, Hyphenate, Convex, Spacetime, SpaceXAI, Atlassian, paste from `docs/devpost.md`, save as draft | Tarun |
| 3 | After the flight: draw the site's zones on the first frame (`ground/sites/editor.html`), fine-tune on our frames, fill the brackets in `docs/devpost.md` | Claude |
| 4 | Demo video under 3 minutes, recorded after the flight | Team |
| 5 | Use Cursor for the final polish (SpaceXAI requires it) | Tarun |
| 6 | At judging: start `ground/demo.sh` at least 45 minutes early so a market has opened and settled on screen | Team |

## Budget

Claude calls are capped at $10 per station session (`BALLOON_SPEND_CAP_USD`, ledger in `ground/out/spend.json`). Grok
voice costs about half a cent per alert. The Anthropic org had about $105 left under its monthly limit on Saturday.
