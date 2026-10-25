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

## Commands

On the station laptop, from the repo root.

**After the flight.** Copy the session off the Pi, then draw the site on one of its stills:

```bash
./fetch.sh tarun@balloon.local <session>         # sessions land in ./data/sessions/
open ground/sites/editor.html                     # load a still, draw lots, spaces, beach, water; save as ground/sites/<session>.json
```

**Live from the balloon** (if it's flying during judging; the station laptop on the same hotspot as the Pi):

```bash
cd ground && .venv/bin/python station.py --pi http://balloon.local:8080 --site sites/<session>.json --agents --prod
```

**Replay a recorded flight** (the fallback, and the default for judging):

```bash
ground/demo.sh data/sessions/<session>                       # loops; Ctrl-C to stop
```

**Clean the public map after a rehearsal:**

```bash
cd web && npx convex run --prod admin:purgeSession '{"session": "<session>"}'   # repeat until counts are 0
```

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
