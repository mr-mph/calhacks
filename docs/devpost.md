# Devpost draft: Soar-on

Paste section by section into Devpost. Anything in [brackets] needs a real fact from the team before submitting
(flight results, the beachgoer conversation). Don't submit a bracket.

**Tagline:** Persistent eye in the sky. A camera that stays over one place for hours, so a beach, a parking lot and a
crowd can see what's happening now.

## Inspiration

Some questions can only be answered from above, right now, for hours. Is a rip current forming at Ocean Beach,
and is anyone in the water near it? How many spaces are open in the lot? Is the crowd on this corner growing?

The tools we have miss one of those three things. A satellite photo is days old and too coarse to see a parking space.
A drone can't stay up for more than 20 to 40 minutes, it's loud, and drones are banned across the Golden Gate National
Parks, which include Ocean Beach and Crissy Field. Ocean Beach also has no lifeguard towers, and SF's coast sees close
to 200 rescues a year.

A small helium balloon on a tether doesn't have those limits. The helium does the lifting, so a power bank only has to
run the camera and computer, and the balloon can stay up for hours, silently, at a fixed spot.

We talked to several beachgoers and swimmers. They told us lifeguards are often far outnumbered by the people in
the water, and that a constant watch from above would make them feel safer.

## What it does

A Raspberry Pi with a downward camera hangs from a tethered balloon 60 to 120 m up and saves a frame every 2 seconds.
A laptop ground station turns each frame into counts, and three groups use them:

- **Beachgoers and patrols.** A model we trained on aerial rip-current imagery flags rips, and a people detector counts
  swimmers near them. Claude writes the alert a patrol member actually reads ("Rip forming north of the stairs, two
  people in the water near it"), with an explicit uncertainty line. A person confirms it on the live map, and the
  confirmed alert becomes a Jira incident assigned to whoever is on shift.
- **Drivers.** Each parking space is marked free or taken on a live map, and a surge-pricing agent sets the lot price
  from occupancy within hard limits: at most one change every 5 minutes, at most 25% per step, a floor and a ceiling,
  and no change when the frame is unreliable. Every decision is logged with its inputs, so "why did the price go up at
  4:10?" has an answer.
- **Markets.** People bet play credits on what the balloon will count ("40 or more cars in lot A at 5 PM?"). A market
  agent proposes markets from the day's history and explains each one. Markets settle on the median of the good frames
  in the minute around the close, and are voided and refunded when there aren't enough good frames.

## How we built it

- **Balloon payload:** Raspberry Pi 4, Logitech webcam, Grove barometer and accelerometer, on a power bank. The Pi
  records stills, video and sensors to its SD card no matter what, and serves a dashboard.
- **Detection:** YOLO11n fine-tuned on VisDrone2019 (real drone imagery, 6,471 training images) for cars and people,
  reaching mAP50 0.72 for cars and 0.31 for pedestrians on the held-out VisDrone set (people are only a few pixels
  tall from above, so we count them and never try to identify anyone). A separate oriented-box model is trained on RipAID (2,186 images,
  CC BY 4.0), validated on two beach cameras it never saw in training: mAP50 0.32 (precision 0.49, recall 0.27), so a
  person confirms every rip alert. [Then fine-tuned
  again on frames from our own flight.]
- **Ground station:** aligns every frame to a reference map of the site (ORB features and RANSAC), so drawn parking
  spaces stay put as the balloon drifts, and scores each frame's confidence from alignment, tilt and count stability.
- **Claude:** Sonnet reads frames for beach alerts; Haiku writes price explanations, proposes markets and explains
  settlements. Numbers always come from our engines, never from the model. A per-session spend cap keeps costs bounded.
- **Convex:** the live map. Frames, observations, prices, decisions and alerts sync to every phone instantly.
- **SpacetimeDB:** the prediction market. Accounts, markets, positions and an LMSR market maker run as a TypeScript
  module on maincloud, with integer money so balances always reconcile. The ground station is the only oracle allowed
  to post counts and settle.
- **Atlassian Forge:** "Balloon Patrol" turns confirmed alerts into Jira incidents: de-duplicates repeats, assigns the
  on-shift lifeguard, escalates when people are in the water, queues low-confidence frames for a human, and writes an
  end-of-shift Confluence report. Every agent action is audited and revertible, and alert text is treated as untrusted
  data, so instructions hidden in it are flagged and ignored.

## Challenges we ran into

- Getting a headless Raspberry Pi onto a network at a venue that bans personal hotspots and isolates Wi-Fi clients. We
  ended up making the Pi's USB-C power cable double as its network link.
- People are only 7 to 11 pixels tall from 100 m, so we count people and never try to identify anyone.
- Keeping an autonomous pricing and market agent honest: guardrails in code, confidence gates, and voiding rather
  than guessing.

## Accomplishments that we're proud of

- [The flight: how high, how long, what it saw.]
- Markets that settle from a live camera count, with money that provably balances.
- An agent whose every action has a reason a judge can read, and that can't be talked into acting differently.

## What we learned

[Two or three honest lessons from the weekend.]

## What's next

Talk to SF Fire's surf rescue team about a trial at Ocean Beach, add a crossing counter for foot-traffic markets, and
use the balloon's sharp labels as ground truth to calibrate satellite counts of the same places.

## Built with

raspberry-pi, python, ultralytics-yolo, opencv, claude, anthropic-api, convex, spacetimedb, typescript, react, vite,
tailwind, atlassian-forge, jira, confluence, vercel, grok, xai, cursor

## Links

- Live map: https://overhead-live.vercel.app
- Markets: https://overhead-market.vercel.app
- Repo: https://github.com/mr-mph/calhacks [make public or add judges, per event rules]

## Track notes (one short paragraph each in the "additional info" fields)

- **Anthropic, Claude for Public Benefit:** community = swimmers and surf patrol at Ocean Beach, SF. Problem: deadly rip
  currents, no lifeguard towers, drones banned. Claude writes the alert, states its uncertainty, never identifies
  anyone, and a human confirms before anything is sent. We talked to several beachgoers and swimmers: lifeguards are often far
  outnumbered by swimmers, and they said a watch from above would make the beach feel safer.
- **Hyphenate, Autonomous Systems for Finance:** two agents (surge pricing, market maker) that do real work on live
  data, act only inside hard limits, log every decision, and stop or void when the data isn't good enough. Roles: lot
  revenue manager, market operator. Real: the counts, the prices, the settlements. Simulated: play-money credits.
- **SpacetimeDB:** the whole market is a SpacetimeDB module: LMSR pricing, scheduled closing, oracle-only settlement,
  live subscriptions to every phone.
- **Convex:** every phone's live map is a Convex live query; the station writes in batches; confirming an alert triggers a
  Convex action that files the Jira incident.
- **Atlassian, track: Best Agent.** Balloon Patrol is an agent that does the patrol's triage in Jira (files, de-duplicates,
  assigns, escalates, writes the shift report), with the security layer built in: audit log, revert, and injection
  defense. Demo site one-atlas-dqcx.atlassian.net. (Devpost asks us to name the track in the description; keep this line.)
- **Microsoft, Built for the Real World:** customers = the Ocean Beach surf patrol and a lot operator. Measurable
  usefulness: seconds from frame to confirmed alert, alerts confirmed vs dismissed, every price change with its logged
  reason. Path to production: runs with zero internet on a Pi + laptop, cloud parts switch on only when configured,
  a per-session Claude spend cap. Responsible design: counts people and never identifies anyone, a human confirms every
  alert, the agents act only inside hard limits, and every action is audited, revertible and injection-resistant.
- **SpaceXAI:** we pulled the freshest free imagery of Ocean Beach and Marina Green from Microsoft Planetary
  Computer and put it next to the balloon's view. Sentinel-2 was 9 days old at 10 m per pixel, so a car is less than
  half a pixel; the sharpest free aerial photo (NAIP, 0.6 m) was from May 2022. The balloon sees about 7 cm per pixel,
  every 2 seconds, so its labels can serve as ground truth for satellite counts of the same place
  (`ground/satellite.py`). Grok's voice API (`/v1/tts`) reads every beach alert aloud on the patrol's phone, so
  nobody has to look at a screen while watching the water. [Built with Cursor: say how the team used it.]
