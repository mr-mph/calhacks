# Overhead: demo video script and recording plan

Target length: under 3:00. Upload to YouTube as Unlisted, paste the link on Devpost.

## Script

| Time | On screen | Voiceover |
|---|---|---|
| 0:00 to 0:08 | Balloon release from the ground, looking up as it climbs | "We built a camera that can sit thousands of feet up and watch one place for hours." |
| 0:08 to 0:15 | Payload close-up (Pi, camera, power bank on the tether) | "Tonight it flies on a tether. The same payload can go much higher." |
| 0:15 to 0:35 | Quick cuts: beach waves, a full parking lot, traffic | "Satellite photos are days old. Drones last twenty minutes and are banned over Ocean Beach. So nobody is watching when a rip current forms, when a lot fills up, or when a disaster hits." |
| 0:35 to 0:45 | Swimmer interview clip, or a still of the beach with the quote as text | "We talked to a swimmer right outside. He said updates within minutes of a rip forming would change everything." |
| 0:45 to 0:58 | Balloon going really high, then the live view looking down (Pi dashboard, `balloon.local:8080`) | "Every two seconds it sends a frame down to our ground station." |
| 0:58 to 1:12 | `ml-traffic-0000271.mp4` then `ml-rip-current.mp4` (sped up) | "Our own models, trained on drone imagery, count every car and person, and flag rip currents, including on beaches they never saw in training." |
| 1:12 to 1:55 | Alerts tab: alert arrives, Grok reads it aloud, tap Confirm, switch to Jira, the incident is there | "When a rip shows up, Claude writes the alert, says how sure it is, and reads it out loud so a lifeguard never has to look at a screen. A person confirms it, and it lands in the patrol's Jira as an incident, assigned to whoever is on shift." |
| 1:55 to 2:20 | Live tab: spaces free and taken, lot price, open "Why did the price change?" | "The same view runs a parking map. An agent sets the lot price from how full it is, inside hard limits, and every change has a reason you can read." |
| 2:20 to 2:30 | Markets site: one market, the odds | "People can even bet play credits on what the balloon will count, settled by the camera itself." |
| 2:30 to 2:45 | One architecture slide: Pi, our models, Claude, Grok, Convex, SpacetimeDB, Jira | "A Raspberry Pi, our own models, Claude, Convex for the live map, SpacetimeDB for the markets, and Atlassian Forge for the patrol." |
| 2:45 to 3:00 | All four of us | Each: name, school, major, one breath. Then: "One balloon, watching so people don't have to." |

## Tabs to have open, left to right

1. `http://balloon.local:8080`: Pi dashboard (Mac or phone on Wi-Fi BalloonNet, password balloon123)
2. `https://overhead-live.vercel.app`: Live tab
3. `https://overhead-live.vercel.app/#/alerts`: Alerts tab. Enter the patrol code, then tap "Read new alerts aloud"
4. `https://one-atlas-dqcx.atlassian.net`: Jira, project BPAT board
5. `https://overhead-market.vercel.app`: markets

Patrol code (run in Terminal):
```
python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/balloon/convex.json')))['patrol_code'])"
```

## Recording order

1. Screen recording: Cmd+Shift+5, "Record Entire Screen", Options: microphone on, turn Mac volume up so Grok's voice is captured.
2. Pi dashboard, 15 s, live video with car boxes.
3. Beach alert: tell Claude "beach". The alert arrives about 15 s later. Let Grok finish reading, tap Confirm, switch to the Jira tab, refresh, open the new incident.
4. Live tab, 25 s: counts, price, "Why did the price change?".
5. Markets, 10 s, only if a market is open.
6. Phone: balloon release and climb, payload close-up, swimmer clip.

## Clips already made

In `assets/generated/` (not in git):

- `ml-traffic-0000271.mp4`, `ml-traffic-0000335.mp4`, `ml-traffic-0000360.mp4`: cars and people boxed by our detector
- `ml-rip-current.mp4`: rip currents highlighted on beach cameras the model never trained on
- `ml-sf-bay-bridge-topdown.mp4`, `ml-sf-bay-bridge.mp4`, `ml-sf-noe-valley.mp4`: San Francisco traffic, real drone video, cars tracked
- `ml-crowd-concert.mp4`: outdoor concert from directly above, people counted
- `ml-parking-lot.mp4`, `ml-parking-busy.mp4`: parking lots from directly above, 100 to 250+ cars counted

Credits if asked: aerial imagery VisDrone2019, beach imagery RipAID (CC BY 4.0), drone video from Pexels (free license).

## Hyphenate beat (autonomous systems for finance)

The surge-pricing agent is the lot's revenue manager. Show, in this order:

1. `ml-crowd-concert.mp4`: "A concert is letting out."
2. `ml-parking-busy.mp4`: "The lot next door is filling up."
3. Live tab, lot price going up, open "Why did the price change?": "The agent raised the price, inside hard limits, and wrote down why."
4. A frame marked unreliable with the price held: "When the camera can't see clearly, it refuses to guess."

Hyphenate asks for the moment the agent catches something or defends a decision. Step 4 is that moment.

## Commands (repo root, Mac on the hotspot or BalloonNet with the iPhone plugged in)

Live from the Pi (detector, live map, markets, agents):
```
NO_NARRATOR=1 ground/start.sh
```

Beach alert replay (Claude runs it when you say "beach"):
```
ground/demo.sh ground/out/sessions/ripaid-standin --no-spacetime
```

Parking replay with markets (start 15 min before filming markets):
```
ground/demo.sh ground/out/sessions/visdrone-standin-0000356
```

## After the flight

- On the dashboard before release: Mark with note "launch".
- The Pi records video and stills the whole time. Bring it back powered on and tell Claude; Claude pulls the recording and cuts the view looking down.

## Devpost before 9:00 AM

- [ ] Video link (YouTube, Unlisted)
- [ ] Every teammate's Hive email and school (Additional info page)
- [ ] Al3x9 and the fourth teammate join: https://devpost.com/software/1507584/joins/dakgVAjv7NFD_R7siLQOOg
- [ ] One sentence on how we used Cursor (SpaceXSI requires it)
- [ ] Swap screenshots for real flight frames, set the thumbnail
- [ ] Repo public, or judges given access (code without a repo isn't judged; `mr-mph/calhacks` is private)
- [ ] Tick Microsoft: Built for the Real World (not ticked yet; track note is in `docs/devpost.md`)
- [ ] No [brackets] left in the description (flight results, "What we learned")
- [ ] Tick the rules box, click Submit (editing stays open until 9:00)
