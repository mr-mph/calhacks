# Demo runbook

Everything the team needs from the flight to the judges' table. Times are Sunday Oct 25 unless noted.

## Timeline

| When | What | Who |
|---|---|---|
| Saturday night | Fly, record a session, copy it to the station laptop (`./fetch.sh`) | SF team |
| Saturday night | Create the Devpost project and save a draft (`docs/devpost.md`) | Tarun |
| After the flight | Draw the site on the first frame, fine-tune on our frames, fill the Devpost brackets | Claude |
| By 8:00 AM | Record the demo video (shot list below), upload it, link it on Devpost | Team |
| **9:00 AM** | **Devpost submission deadline (hard)** | Tarun |
| 9:30 AM | Start the replay (below) so a market opens and settles before judges arrive | Station laptop |
| 10:30 AM | Be at the assigned table, **whole team present** | Team |
| 10:30 AM to 12:30 PM | Judging: 2 to 3 minute pitch with a live demo | Team |

## Tonight in SF

The Pi runs its own Wi-Fi, BalloonNet, at 10.42.0.1. Run everything on the station laptop from the repo root, on an
up-to-date `main`.

**1. Network.** Join BalloonNet. It has no internet, so give the laptop a second link (iPhone USB tethering or
Ethernet) and drag that service above Wi-Fi in System Settings > Network > Set Service Order. Both checks must pass:

```bash
curl -s http://10.42.0.1:8080/api/status | head -c 120; echo                 # the Pi
curl -s -o /dev/null -w "%{http_code}\n" https://agreeable-penguin-576.convex.cloud/version   # internet: 200
```

**2. Station prerequisites** (once per laptop; skip what's already there):

```bash
ls ground/runs/visdrone/weights/best.pt ground/runs/ripaid/weights/best.pt   # missing: copy from Tarun's Mac
ls ~/.config/balloon/convex.json ~/.config/balloon/spacetime.json             # missing: map and markets stay off
(cd ground && test -x .venv/bin/python || (python3 -m venv .venv && .venv/bin/pip install -r requirements-station.txt))
ssh tarun@10.42.0.1 true                                                      # fails: ssh-copy-id tarun@10.42.0.1
```

**3. Update the Pi and check it.** Deploying restarts the services, which starts a new session, so do it before launch:

```bash
./deploy.sh tarun@10.42.0.1
ssh tarun@10.42.0.1 /opt/balloon/tools/preflight.sh
```

**4. Calibrate on the ground**, payload hanging still. Replace 5 with the ground elevation of the spot in metres:

```bash
curl -s -X POST http://10.42.0.1:8080/api/level; echo
curl -s -X POST -H 'Content-Type: application/json' -d '{"elevation_m": 5}' http://10.42.0.1:8080/api/elevation; echo
```

At release, press Mark on the dashboard with the note "launch", or:

```bash
curl -s -X POST -H 'Content-Type: application/json' -d '{"note": "launch"}' http://10.42.0.1:8080/api/mark; echo
```

**5. Start the station.** It sends frames and counts to the public map, counts to the markets, and boxes back to the
Pi's dashboard (http://10.42.0.1:8080 on any phone on BalloonNet). Without a site you get whole-frame counts only:

```bash
cd ground && .venv/bin/python station.py --pi http://10.42.0.1:8080 --agents --prod
```

**6. Add the site once the view is steady.** Open a still from http://10.42.0.1:8080/data/sessions/ (the current
session is in `/api/status`), save it into `ground/sites/`, open `ground/sites/editor.html`, load that still, draw the
lots, spaces, beach and water, and save the JSON into `ground/sites/` next to the still. Live mode looks for the
reference still next to the JSON. Then restart the station with the site:

```bash
cd ground && .venv/bin/python station.py --pi http://10.42.0.1:8080 --site sites/<site>.json --agents --prod
```

**7. After the flight**, copy the session to the laptop for the replay:

```bash
./fetch.sh tarun@10.42.0.1 <session>
```

## Commands

On the station laptop, from the repo root.

**After the flight.** Copy the session off the Pi, then draw the site on one of its stills:

```bash
./fetch.sh tarun@10.42.0.1 <session>             # sessions land in ./data/sessions/
open ground/sites/editor.html                     # load a still, draw lots, spaces, beach, water; save as ground/sites/<session>.json
```

**Live from the balloon** (if it's flying during judging; the station laptop on BalloonNet, see "Tonight in SF"):

```bash
cd ground && .venv/bin/python station.py --pi http://10.42.0.1:8080 --site sites/<session>.json --agents --prod
```

**Replay a recorded flight** (the fallback, and the default for judging):

```bash
ground/demo.sh data/sessions/<session>                       # loops; Ctrl-C to stop
```

**Clean the public map after a rehearsal:**

```bash
cd web && npx convex run --prod admin:purgeSession '{"session": "<session>"}'   # repeat until counts are 0
```

The purge is an internal function, so run it in a checkout where `npx convex dev` has linked the web project once. A
fresh checkout fails with "No CONVEX_DEPLOYMENT set".

## Before judges arrive

- Start the replay at least 45 minutes early. The market agent opens its first market after about 10 minutes, and a
  settled market (with Claude's explanation) is the strongest thing on the Markets page.
- Open three tabs on a phone and a laptop: https://overhead-live.vercel.app, https://overhead-market.vercel.app, and the
  Jira board on https://one-atlas-dqcx.atlassian.net (project BPAT).
- On the phone: enter the patrol code on the Alerts tab and turn on "Read new alerts aloud" (the tap is what lets the
  phone play sound).
- Register a name on the Markets page and place one small bet so the "your position" row shows.
- Check the Claude spend: `ground/out/spend.json` (cap $10 per session).

## Pitch (about 2.5 minutes)

1. **The problem, one line each.** A satellite photo of Ocean Beach is 9 days old at 10 m per pixel, so a car is less
   than half a pixel. Drones last 20 to 40 minutes and are banned across the Golden Gate National Parks. Lifeguards are
   outnumbered; the beachgoers we talked to said a watch from above would make them feel safer.
2. **The balloon.** A $35 Pi and a webcam on a tether, about 7 cm per pixel, every 2 seconds, for hours.
3. **Live map.** Spaces lighting up free and taken, the lot price, and "why did the price change?".
4. **Beach alert.** A rip flagged by our rip model, Claude's alert with its uncertainty line, read aloud by Grok,
   confirmed by a patrol member, and the Jira incident appearing on the patrol's board.
5. **Markets.** A market on the lot's count, its odds, and a settled market with the observed value and Claude's
   explanation.
6. **Close.** One balloon, three groups served, every decision logged, and a person in the loop wherever it matters.

Expected questions: *How accurate is it?* Cars mAP50 0.72, pedestrians 0.31, rips 0.32 on cameras the model never saw,
so a person confirms every alert. *What about wind?* Frames that don't line up or tilt too far get low confidence;
prices hold and markets void instead of guessing. *Is it legal?* A small tethered balloon falls outside the FAA's
moored-balloon rules (over 6 ft or 115 cu ft).

## Demo video shot list (under 3 minutes)

1. 0:00 to 0:15. The balloon going up, and the view from it.
2. 0:15 to 0:40. The problem: satellite tile next to the balloon frame (`ground/satellite.py compare`).
3. 0:40 to 1:20. Live map on a phone: spaces, counts, a price change and its reason.
4. 1:20 to 2:00. A beach alert: drafted, read aloud, confirmed, the Jira incident created.
5. 2:00 to 2:40. Markets: bet, live odds, a settlement with its explanation.
6. 2:40 to 3:00. Architecture in one slide (Pi, station, Claude, Convex, SpacetimeDB, Forge) and the team.

Hyphenate wants the video to open with "the moment" (the agent catching something, recovering, or defending a
decision), so cut a version that starts with step 4 or a market voiding on bad frames.
