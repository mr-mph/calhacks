# Soar-on Markets

Live at maincloud database **`overhead-market`** (`wss://maincloud.spacetimedb.com`).

Prediction markets on what the balloon camera counts ("40 or more cars in lot A at 5:00 PM?"). People bet play
credits from their phones; the ground station posts counts and settles. SpacetimeDB is the whole backend: every
bet, price, position and settlement is a reducer call, and every phone sees it instantly through subscriptions.

```
server/   SpacetimeDB module (TypeScript): tables, reducers, LMSR market maker
web/      Phone-first page (Vite + TypeScript, no framework) subscribed to the module, styled per docs/design.md
scripts/  smoke.sh (end-to-end test), seed-demo.sh (demo data), lib.sh (curl helpers)
assets/generated/  screenshots of the page at 390 px and desktop
```

## Run locally

Needs the SpacetimeDB CLI 2.13 (`~/.local/bin/spacetime`), Node 22+, pnpm, curl and jq.

```bash
spacetime start                                  # local server on :3000, leave running

cd market/server && pnpm install && cd ..
export ORACLE_SECRET=$(openssl rand -hex 24)     # keep it; the station needs it
spacetime publish balloon-market --server local --module-path server --yes

scripts/seed-demo.sh                             # optional: 3 markets, trades, counts (fresh database only)

cd web && pnpm install && pnpm dev               # http://localhost:5174, and http://<laptop-ip>:5174 on phones
```

Which database the page talks to is fixed at build time (`web/src/config.ts`):

| Command | Server | Database |
|---|---|---|
| `pnpm dev` | `ws://<page host>:3000` (the laptop, also from phones on the LAN) | `balloon-market` |
| `pnpm dev:cloud`, `pnpm build` | `wss://maincloud.spacetimedb.com` | `overhead-market` |

The Live and Alerts tabs link to the map app (`web/`): its dev server on port 5173 for `pnpm dev` (this page runs
on 5174), `https://overhead-live.vercel.app` for builds. `VITE_SPACETIME_URI`, `VITE_SPACETIME_DB`, `VITE_LIVE_URL`
and `VITE_ALERTS_URL` override any of these. After changing the module, run
`pnpm generate` in `web/` to refresh the bindings.

Run the end-to-end test. It publishes a throwaway database and wipes it each run, so it never touches real data:

```bash
scripts/smoke.sh                                                    # local, database balloon-market-smoke
SPACETIME_HOST=https://maincloud.spacetimedb.com SMOKE_DB=overhead-market-smoke SMOKE_CLOSE_SECONDS=25 \
  scripts/smoke.sh                                                  # maincloud, separate throwaway database
```

## How the market works

- **Accounts.** `register(name)` gives the caller's identity 1000 credits. Money is stored as integer
  micro-credits (`balance_micro`), so balances never drift.
- **Pricing.** Each market is an LMSR market maker with liquidity `b`:
  `C(q) = b * ln(e^(q_yes/b) + e^(q_no/b))`, `price_yes = e^(q_yes/b) / (e^(q_yes/b) + e^(q_no/b))`.
  Buying costs `C(q') - C(q)`, computed with log-sum-exp and rounded up to the micro-credit, so the trader absorbs
  rounding, never the maker. Each winning share pays 1 credit.
- **Pool and subsidy.** A market opens with a pool equal to its subsidy, `b * ln 2` (69.31 credits at b = 100).
  Every trade adds its cost to the pool and winners are paid from it. LMSR caps the maker's loss at that subsidy, so
  the pool can never go negative; `settle` refuses if it would. The invariant the smoke test checks:
  `sum(balances) + sum(pools) = credits granted + sum(subsidies)`.
- **Closing.** `create_market` schedules a `close_market` reducer at `close_at` (a SpacetimeDB scheduled table), so
  markets close on time with no cron. `buy` also rejects anything at or after `close_at`.
- **Settlement.** `settle(market_id, value, explanation)` takes the observed value; the module applies the market's
  own comparator and threshold, so the oracle reports a number, not a winner. Positions on the winning side get
  1 credit per share. `void_market(market_id, reason)` refunds every position exactly what it paid.
- **Why.** `create_market` takes a one-sentence `rationale` from the market agent (why this threshold, why now).
  The page shows it as the card's "Why" line, then shows the settlement explanation once the market resolves.
- **What the station decides.** Per `docs/architecture.md`: the value is the median count over frames within 60 s
  of close with confidence of at least 0.5; too few good frames means void. The explanation should say that in
  plain words. The module stores it on the market and the page shows it.

Tables (all public, so anyone can audit): `account`, `market`, `position`, `trade`, `observation`,
`latest_observation` (one row per zone/metric for the live count on phones), `oracle`. `close_timer` is private.

## Oracle model

Only identities in the `oracle` table can call `create_market`, `post_observation`, `settle` and `void_market`.
An identity becomes an oracle by calling `claim_oracle(secret)` with the value of `ORACLE_SECRET`.

- `ORACLE_SECRET` is a **required module environment variable** (SpacetimeDB 2.x `schema(..., { env })`). The host
  refuses to publish without it, it is never in the repo or the compiled module, and clients cannot read it.
  The reducer refuses claims if the secret is shorter than 24 characters, and compares in constant time.
- Each service gets its own identity (the station, the market agent), so a leaked station token does not expose
  the publisher's CLI login, which can delete the database. Every market, observation and settlement records
  which identity made it.
- Oracles cannot trade: whoever reports the settling value holds no position in it.
- Known limit: identities are free, so one person can register many accounts and collect 1000 credits each. Fine
  for play money; gate `register` behind a join code if a leaderboard ever matters.
- Rotate the secret without redeploying code: `ORACLE_SECRET=<new> spacetime publish <db> --env-only`.
  Rotation stops new claims; identities that already claimed stay oracles. There is no revoke reducer yet; wiping
  the database (`--delete-data=always`) is the only way to remove one.

Why not "the publisher is the oracle"? It would force the station to run with the owner's personal token. The
shared secret is the simplest option the 2.x API offers that gives each service a separate, limited identity.

## HTTP calls for the station (no JS client needed)

All verified against the local server and maincloud by `scripts/smoke.sh`. Maincloud issues anonymous tokens from
`POST /v1/identity` the same way the local server does.

| What | Request |
|---|---|
| New identity + token | `POST /v1/identity` returns `{"identity": "...", "token": "..."}`. Save the token. |
| Call a reducer | `POST /v1/database/<db>/call/<reducer>` with `Authorization: Bearer <token>`, body = JSON array of positional args |
| Read data | `POST /v1/database/<db>/sql`, body = SQL text, e.g. `SELECT * FROM market WHERE status = 'closed'` |

Success is HTTP 200 with an empty body. A rejected call (bad secret, not an oracle, market not closed) is HTTP 530
with the reason as plain text.

Reducer arguments, in order:

| Reducer | Args |
|---|---|
| `claim_oracle` | `secret` |
| `create_market` | `question, zone, metric, comparator (">=" ">" "<=" "<"), threshold, close_at_unix (seconds, within 7 days), b (10..10000), rationale` |
| `post_observation` | `t (unix seconds, at most 60 s ahead of the server clock), zone, metric, value, confidence (0..1), frame` |
| `settle` | `market_id, value, explanation` |
| `void_market` | `market_id, reason` |
| `register` / `buy` | `name` / `market_id, side ("yes" or "no"), shares (1..1000)` (phones use these) |

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:3000/v1/identity | jq -r .token)
curl -X POST http://127.0.0.1:3000/v1/database/balloon-market/call/claim_oracle \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "[\"$ORACLE_SECRET\"]"
curl -X POST http://127.0.0.1:3000/v1/database/balloon-market/call/post_observation \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '[1792880000.0, "lot-a", "car_count", 37, 0.86, "stills/000456.jpg"]'
```

Python, stdlib only (the station uses `ground/spacetime_sink.py`, which does the same with requests):

```python
import json, os, urllib.error, urllib.request

CFG = json.load(open(os.path.expanduser("~/.config/balloon/spacetime.json")))
BASE, DB = CFG["host"], CFG["database"]

def new_token() -> str:
    with urllib.request.urlopen(urllib.request.Request(f"{BASE}/v1/identity", method="POST"), timeout=5) as r:
        return json.load(r)["token"]

def call(token: str, reducer: str, *args) -> None:
    req = urllib.request.Request(
        f"{BASE}/v1/database/{DB}/call/{reducer}",
        data=json.dumps(list(args)).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{reducer} rejected ({e.code}): {e.read().decode()}") from e

token = CFG["station_token"]              # already an oracle; new_token() + claim_oracle only for a new service
call(token, "post_observation", obs["t"], "lot-a", "car_count", obs["zones"]["lot-a"]["car"], obs["confidence"], obs["frame"])
call(token, "settle", market_id, 42, "Median of 28 frames within 60 s of 5:00 PM was 42 cars (confidence >= 0.8).")
```

## Maincloud

Published as `overhead-market` (dashboard: https://spacetimedb.com/overhead-market), owned by the CLI login.
The station's copy of everything it needs lives outside the repo, readable only by the owner:

```
~/.config/balloon/spacetime.json   (chmod 600)
{ "host", "database", "oracle_secret", "station_identity", "station_token" }
```

`station_token` already holds an oracle identity, so the station just sends it as the bearer token. Other services
(the market agent) should call `POST /v1/identity` for their own token and `claim_oracle` with `oracle_secret`.

Republish after module changes. Environment values are kept between publishes, so no secret is needed:

```bash
cd market
spacetime publish overhead-market --server maincloud --module-path server --yes
cd web && pnpm generate && vercel build --prod && vercel deploy --prebuilt --prod   # https://overhead-market.vercel.app
```

The page is Vercel project `overhead-market`. It is built on the laptop (`--prebuilt`) because it imports the LMSR
math from `server/src`, which a deploy of `web/` alone would not upload.

Add columns with `.default(...)` so the publish migrates in place. `--delete-data=always` wipes every account,
market and oracle claim, after which the station must claim again.

Rotate the secret, then update `oracle_secret` in the config file:

```bash
ORACLE_SECRET=$(openssl rand -hex 24) spacetime publish overhead-market --server maincloud \
  --module-path server --env-only --yes
```
