# Why a balloon

**Claim:** a $100 tethered balloon can watch the lowest 100 m of air over a fire-prone site for hours, and that thin slice
decides when a fire wakes up and where its smoke goes. Weather stations only see the ground. Drones can't stay up
for long, and their rotors mix the very air they're trying to measure.

## The fire-weather idea in one paragraph

At night, cool air pools near the ground under a layer of warmer air. This is a temperature *inversion*. It acts as a lid:
smoke stays trapped low, and a fire calms down. In the late morning the sun heats the ground until the inversion
breaks. Fresh air reaches the fire and smoke lofts away, and fire activity often jumps within the hour. Fire crews are
trained to watch for this. But the nearest place that measures the air above the ground is the Oakland weather balloon,
launched twice a day. Our balloon measures it continuously, at one site, through the hours when the inversion breaks.

## Balloon vs. the alternatives

| | Tethered balloon (us) | Drone | Weather station (RAWS) | High-altitude balloon |
|---|---|---|---|---|
| Time aloft | Hours (lift costs no power; a 10,000 mAh bank runs the Pi about 6 h) | 20–45 min per battery | Always on | One 2–3 h flight, then it's lost or recovered |
| Measures the air above the ground | Yes, 0–100 m, repeatedly | Yes, but rotor wash disturbs the readings | No, one point at 6 m | Passes the low layer in about a minute, once |
| Disturbs what it measures | No: passive, silent, no downwash | Yes: rotors mix air and bias temperature/pressure near the surface | No | No |
| Wind | Measured: tether angle and sway *are* the wind | Wind is noise the autopilot fights | Measured at 6 m | Drift gives the wind once, then it's gone |
| Can fly at Crissy Field / Presidio | Small tethered balloon, outside FAA moored-balloon rules | No: the National Park Service bans drones in all of Golden Gate National Parks | n/a | No: it drifts out over the city and the Bay |
| Live demo for judges | Yes, dashboard over Wi-Fi the whole time | Yes, for 20 minutes | n/a | No: the data comes back after recovery |
| Operator | Anyone holding a line | A licensed pilot, plus LAANC approval near SFO | n/a | Launch and chase team |
| Cost | About $100 of helium plus a $35 Pi | $500–$2,000 | ~$15k | $300+ per flight, hardware often lost |

**Why not go higher?** Thirty kilometres up makes great photos, but local fire risk lives in the bottom few hundred
metres. A free balloon also can't be demoed live and is usually lost. Height isn't the useful part. What matters is
staying at the right height for hours.

## What we measure

| Sensor | Raw reading | What we turn it into | Why it matters for fire |
|---|---|---|---|
| BMP280 barometer | pressure, temperature | altitude (±1 m relative); temperature vs. altitude | lapse rate: is there an inversion, how deep, and is it breaking |
| Accelerometer | 3-axis g | tilt from vertical, sway variance | wind speed (tether angle) and gustiness (sway) |
| Air Quality v1.3 (A4) | analog gas level | relative gas/smoke level vs. altitude | smoke-layer height: where the dirty air stops |
| USB webcam (looking down) | stills every 2 s | mosaic map of the ground | vegetation greenness and haze, mapped |
| Pi stats | CPU temp, RSSI, disk | health | preflight GO / NO-GO |

## What we compute from it

Items 1–3 are physics, cheap enough to run on the Pi with numpy. Items 4–5 are vision. Item 6 is the language layer, run on a laptop.

1. **Inversion detector.** Fit temperature against altitude on each climb. A positive slope means an inversion. Report
   its height and strength, and flag the moment it breaks (the slope goes negative near the ground).
2. **Wind from the tether angle.** At equilibrium, tan(tilt) = drag / net lift, and drag = ½ρv²·Cd·A, so the tilt gives
   the wind speed. For a 36" balloon with 300 g of net lift, the tilt is about 28° at 3 m/s and about 56° at 5 m/s, so
   this works best in light wind. Calibrate it once against a phone anemometer or the nearest station.
3. **Smoke-layer height.** Find the altitude where the air-quality reading drops off on the climb. Below that height
   people are breathing the smoke.
4. **Fuel greenness map.** VARI = (G − R) / (G + R − B) is a vegetation index that works with an ordinary RGB camera.
   Run it on each still and on the mosaic to colour live (green) and cured (brown) fuel.
5. **Haze score.** The dark-channel prior estimates haze density from a single image. It's cheap on the Pi, and it gives
   a smoke indicator from the camera that backs up the gas sensor.
6. **Fire-weather brief.** Send the numbers and a few stills to Claude on the laptop. It returns a plain-language
   brief, e.g. "Inversion at 60 m, breaking. Gas reading 3x higher below it. Wind 4 m/s and rising. About 70% of
   visible fuel is cured. Expect activity to pick up within the hour." This is the line a fire crew or a school
   principal would actually read.

The dashboard already has the vertical profiles, mosaic and replay. Items 1–6 are new work on top of that.

## Demo storyline (3 minutes)

1. A fire starts the same way every day: it's quiet at night and wakes up when the inversion breaks. Nobody measures that layer where the fire is.
2. Here's our balloon. It's live now, at N metres. (Dashboard on the projector, QR code for judges' phones.)
3. Walk the climb: the temperature profile, the air-quality profile, and the wind from the tilt. Point at where the inversion is.
4. The mosaic, coloured by fuel greenness.
5. Claude's brief. Then close: it costs $100, can be set up anywhere, and can stay up for hours.

## Sponsor tracks that fit

Ranked by fit. These are from the Cal Hacks 13.0 Devpost prize list.

| Track | Prize | Fit | What it takes |
|---|---|---|---|
| Cal Hacks Best Hardware Hack | Bambu Lab 3D printer each | Strong | Nothing extra, this is a hardware hack |
| Cal Hacks Best Planet-First Social Impact Hack | America the Beautiful parks pass each | Strong | The wildfire angle; the parks-pass prize matches the national-park point |
| Cal Hacks Overall / Most Technically Advanced / Most Creative | $3,600 + laptops / keyboards / cameras | Medium–strong | Physics inference + vision + live hardware |
| [Microsoft] Built for the Real World | $3,800 + Surface each | Medium | Frame it as a deployable field tool (cost, operator, persistence) |
| [MLH] Best Use of Tiger Data | Stream Deck Mini | Strong technical fit | Push telemetry to a Tiger (Postgres time-series) instance from the laptop side; their brief names "real-time IoT monitoring" |
| [MLH] Best Use of Gemini API | MLH swag | Low value | Only if we use Gemini for the vision step |
| [SpaceXSI] Make it Legendary | $400 + keyboards | Weak | Requires building with Cursor; could pair NASA FIRMS satellite fire data with balloon ground truth |
| [MLH] Commit Fellowship | Founder sprint interview | Optional | Only if someone wants to keep going after the hackathon |

No sponsor track rewards using Claude, even though Anthropic presents the event. Item 6 is still worth building,
because it's what turns raw numbers into something a person can act on.

Judging criteria are Application, Intentionality, Functionality, Creativity and Technical Complexity. The table
answers Application, the live dashboard answers Functionality, and items 1–5 answer Technical Complexity.

## Honest limits (say these before a judge does)

- The air-quality sensor is uncalibrated and responds to many gases. We report *relative* changes with altitude, not ppm.
- Sun heats a sensor inside a foam box. Mount the BMP280 outside the box, shaded and ventilated, or the temperature
  profile shows the box, not the air.
- Wind from the tilt is an estimate and saturates above about 6 m/s. Bay Area afternoon wind can push the balloon almost
  flat, so fly in the morning or early evening.
- 100 m is only the bottom of a typical nighttime inversion (often 100–300 m deep). We show the method; a taller tether scales it.
- A tethered balloon is still in the airspace. Keep it low, marked and attended. Firefighting aircraft fly low, which is
  why "If you fly, we can't" applies to anything airborne near an active fire.

## Sources

- Cal Hacks 13.0 prize list: https://cal-hacks-13-0.devpost.com/
- NPS drone ban, Golden Gate National Parks: https://www.parksconservancy.org/node/240 and https://home.nps.gov/subjects/policy/upload/PM_14-05.pdf
- FAA Part 101 moored-balloon threshold (6 ft diameter / 115 cu ft): https://www.gombergkites.com/faq/faq-faa.html
- Rotor downwash affects drone temperature and pressure readings: https://calhoun.nps.edu/entities/publication/be5c5b73-e54c-4bd5-85c5-cef6747acf2e and https://www2.mdpi.com/2504-446X/6/9/253
