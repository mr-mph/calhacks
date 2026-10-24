# Launch plan: helium and lift

Rule of thumb: helium lifts about 1 kg per m³ (about 28 g per cu ft) at sea level, gross. Subtract the balloons' own mass.

## How much helium

Weigh the payload first. The budget in CLAUDE.md is ~400 g; add ~150 g for line, fittings and margin.

| Payload + rigging | 11" party balloons (~10 g net each) | 36" balloons (~250 g net each, full) | Helium |
|---|---|---|---|
| 0.55 kg | ~55 | 3, carry 4 | ~35 cu ft |
| 1.2 kg | ~120 to float, ~150 to climb | 5–6, carry 7–8 | ~75–80 cu ft |

- Bigger balloons cut the count and the tying, not the helium. With 3–4 balloons, one pop loses 25–30% of lift: carry spares.
- A balloon filled to its rated size can't expand as pressure drops. Fine on a tether; underfill for anything free-flying.
- Every 100 g cut saves about 10 party balloons and 5 cu ft of helium.

## Where to get it (Saturday)

| Place | What | Hours |
|---|---|---|
| Berkeley Balloons and Events, 1643 San Pablo Ave, 510-932-5537 (texts OK) | Latex balloons, helium fills; ask about 36" stock and tank rental | Mon–Sat 9am–6pm |
| Airgas Berkeley, 1224 6th St | Industrial helium cylinders | Closed weekends |
| Safeway, 1444 Shattuck Place | Pre-inflated balloons only | 5am–midnight |

Ask the balloon shop three things: uninflated 36" latex (or ~60 11"), a rented tank with regulator and nozzle, and the price.
Rental runs about $0.50–1.50 per cu ft; disposable tanks (8.9 / 14.9 cu ft) about $2.50–4.00 per cu ft.

## Tether

30–50 lb braided line and gloves (REI Berkeley, 1338 San Pablo Ave, opens 10am; call 510-527-4140 to check stock).
A balloon cluster pulls hard on thin line, so wear the gloves.

## Order of the day

1. 9am: balloon shop (helium, balloons).
2. 10am: REI (line, gloves).
3. Tethered lift test with a partial fill before the real run; `ssh tarun@balloon.local /opt/balloon/tools/preflight.sh` before release.

If helium falls through: do the sensor and camera dry run on the ground and use replay mode for the demo.
