# Why a balloon

**Claim:** a tethered balloon a few hundred feet up is a camera that can watch one place for hours, at a level of
detail satellites can't reach and for longer than any drone battery lasts. We use that one view to serve three groups
of people: beachgoers, drivers, and the analysts who already pay for satellite photos of parking lots.

## Balloon vs. drone vs. satellite

| | Tethered balloon (us) | Drone | Satellite |
|---|---|---|---|
| Watches one place continuously | Hours: helium does the lifting, and the power bank only runs the Pi (3–4 W, about 15 h on 20,000 mAh) | 20–40 min per battery | No. It passes over, then returns hours or days later |
| Ground detail | ~7 cm per pixel (1080p webcam at 100 m) | Similar | ~30 cm at best (top commercial satellites); free Sentinel-2 is 10 m |
| Sees change through the day | Yes, a full time series | Only while the battery lasts | One snapshot per pass |
| Allowed over Ocean Beach, Crissy Field, the Presidio | Small tethered balloons fall outside the FAA moored-balloon rules | No: the Park Service bans drones in all of Golden Gate National Parks | n/a |
| Operator and noise | Anyone holding a line; silent | Licensed pilot; loud | n/a |
| Cost | ~$150 of helium plus a $35 Pi | $500–2,000 | Pay per image |

How much one frame covers, for a webcam with a ~70° horizontal field of view:

| Height | Ground width | 1080p detail | A car is | A person is |
|---|---|---|---|---|
| 200 ft (61 m) | ~85 m | ~4 cm/px | ~100 px | ~11 px |
| 330 ft (100 m) | ~140 m | ~7 cm/px | ~60 px | ~7 px |

Cars and rip currents are easy targets. A rip current shows up as a dark gap tens of metres wide in the line of
breaking waves. A single swimmer is small, so we detect "person in the water" rather than identify anyone. Run the
camera at 1080p for stills; the stream can stay at 640x480.

## One view, three customers

### 1. Beachgoers at Ocean Beach (public benefit)

Ocean Beach has strong rip currents and nearly 200 rescues a year along SF's coast, most of them there. It has no
lifeguard towers, because officials worry a tower would suggest the water is safe to swim. Drones are banned there.
A balloon over the beach can:

- flag rip currents as they form (the dark gaps in the surf line);
- count people in the water and point at anyone beyond the break;
- have Claude write the alert a patrol or a parent actually reads: "Rip forming 150 m north of the Lincoln stairs.
  Two people in the water near it."

**Before judging, talk to one real person**, such as an SFFD beach patrol member, a surfer, or a parent at the beach.
Anthropic's judges ask for a named community and a problem "you have lived or talked to someone who has".

### 2. Drivers (parking)

From above, a lot is a grid. We mark each space open or taken and push a live map to phones. It's the easiest
detection problem we have, and a good first model to train.

### 3. Analysts (finance)

Hedge funds already buy satellite car counts of retail parking lots to predict earnings. A Berkeley Haas study of
7.6 million satellite images across 44 retailers found the counts anticipate earnings news. Orbital Insight tracks
about 250,000 lots this way. But a satellite gets one snapshot a day at best. A balloon gives the whole curve: when
the lot fills, how long people stay, and foot traffic past a storefront. We sell that time series, and an agent
turns it into a signal.

## What we build

1. **Detector (our own model).** Start from a small pretrained detector (YOLO-nano). Fine-tune it on public aerial
   datasets: CARPK and PKLot for parking, and the published aerial rip-current dataset. Then fine-tune again on
   frames from our own flights: auto-label them with a large vision model, correct about 200 by hand, and train.
   The last step makes it our model, trained on our balloon's view. It runs on the laptop, or at a few frames per
   second on the Pi.
2. **Live map and alerts.** Detections go to a real-time backend (Convex or Spacetime), and phones get a live
   parking map and beach alerts.
3. **Claude layer.** Claude reads each frame together with the detections. It writes the beach alert, flags low
   confidence (glare, fog, a tilted frame), and drafts the analyst's note.
4. **Already working** on the Pi: stills every 2 s, video, sensors, replay, timelapse, and the Pi as its own Wi-Fi
   network ("BalloonNet").

## Sponsor tracks

Every project is automatically considered for the Cal Hacks prizes. Sponsor prizes are opt-in on Devpost, and we
found no limit on how many we can enter. Each one does add a build requirement, so pick two or three.

| Track | What it is | Prize | What it would take from us | Fit |
|---|---|---|---|---|
| Cal Hacks: Best Hardware, People-First, Planet-First, Overall | Automatic | Bambu A1 Mini each; Apple Watch; Parks Pass; MacBook Air | Nothing extra | Strong |
| **Anthropic: Claude for Public Benefit** | Build with Claude for a *named community* with a real problem | $5k Claude credits + 1 yr Max 20x | The beach story, plus one conversation with a real beachgoer or patrol member | Strong |
| **Hyphenate: Autonomous Systems for Finance** | An autonomous agent that does real finance work | $8k / $5k / $3k | An analyst agent: balloon counts in, a signal and a memo out, with a log of its work, and it says when it isn't sure | Strong, and the biggest cash prize |
| **Convex** | Reactive TypeScript backend: database, functions and live sync in one | $5,000 (one winner) | The live map and alerts run on Convex. Convex also has an alpha ESP32 client (github.com/convex/convex-esp32), which suits a hardware hack | Good. Pick Convex *or* Spacetime, not both |
| Spacetime | Database and server logic with real-time sync | $2,048 / $1,024 / $512 | Same role as Convex | Good |
| Microsoft: Built for the Real World | A production-minded AI agent | Surface laptop each | Show customer understanding, measurable usefulness and a path to production | Medium |
| SpaceXAI: Make it Legendary | "Real space data goes in and a legendary project comes out" | Cursor keyboard (Devpost also lists $400) | Must be built in Cursor; the Hacker Guide also requires the Grok Imagine or Voice API, while Slack lists Grok only as a bonus, so ask at their booth. Our space angle: the balloon is *ground truth for satellites*. Its 7 cm labels (cars, crowd) train or check a model on free Sentinel-2 tiles of the same place, and Grok Voice reads the alerts | Doable; small prize |
| Coinbase x402 | Pay-per-request payments for APIs and agents | $500 USDC per member | Sell balloon counts per request ("cars in lot X, last hour") through x402 | Fits the "market for counts" idea |
| Atlassian Agentic Workforce | A Forge app for Jira or Confluence: an agent that does team work, or security for such agents. Judged on idea, usefulness to Atlassian users, and use of Forge | AirPods Max | A Jira agent for the beach patrol: each balloon alert becomes a Jira incident with the frame attached, routed to whoever is on shift, and the day's log becomes a Confluence report. Needs Forge CLI setup and a demo site (about 15 min) | Possible, small prize, extra build |

## Demo storyline (3 minutes)

1. A satellite photo of the beach: one picture, days old. Our balloon: live, over the same beach.
2. The live map: open parking spaces turning green, and people in the water boxed.
3. A rip forms in the replay, and Claude's alert appears on a phone.
4. The analyst view: the lot's fill curve for the day next to the single satellite snapshot, and the agent's note.
5. Close: one $150 balloon, hours aloft, and three groups who need what it sees.

## Honest limits

- A person is only a few pixels across, so we count people, not identify them, and the alerts say so.
- Wind tilts the camera and fog hides the water. The Claude layer reports low confidence instead of guessing.
- Our fine-tuning set is small. We'll quote accuracy on frames held out from training.

## Sources

- Cal Hacks 13.0 prizes: https://cal-hacks-13-0.devpost.com/ and the Hacker Guide
- Park Service drone ban, Golden Gate National Parks: https://www.parksconservancy.org/node/240
- FAA Part 101 moored-balloon threshold: https://www.gombergkites.com/faq/faq-faa.html
- Ocean Beach rescues and the lifeguard-tower debate: https://cbsnews.com/amp/sanfrancisco/news/ocean-beach-drowning-renews-debate-over-need-for-lifeguards and https://abc7news.com/16535717
- Satellite parking-lot counts and earnings (Berkeley Haas): https://newsroom.haas.berkeley.edu/how-hedge-funds-use-satellite-images-to-beat-wall-street-and-main-street/
- Orbital Insight's 250,000 tracked lots: https://theoutline.com/post/1169/jc-penney-satellite-imaging
