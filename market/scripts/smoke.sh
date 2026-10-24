#!/usr/bin/env bash
# End-to-end check of the market module over the same HTTP API the ground station uses.
# Needs a running local server (`spacetime start`), curl and jq. Wipes and republishes DB each run.
set -euo pipefail

HOST="${SPACETIME_HOST:-http://127.0.0.1:3000}"
DB="${SMOKE_DB:-balloon-market-smoke}"
SECRET="smoke-secret-$(date +%s)-abcdefghijklmnop"
MICRO=1000000
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib.sh
source "$HERE/scripts/lib.sh"

pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; exit 1; }

expect_ok() {
  local res; res=$(call "$@")
  [[ $res == 200* ]] || fail "$2 $3 -> $res"
}

expect_err() {
  local want="$1"; shift
  local res; res=$(call "$@")
  [[ $res != 200* && $res == *"$want"* ]] || fail "$2 should fail with '$want', got: $res"
  pass "$2 rejected: ${res#* }"
}

balance_of() { scalar "SELECT balance_micro FROM account WHERE name = '$1'"; }

echo "publishing $DB to $HOST"
ORACLE_SECRET="$SECRET" "${SPACETIME:-spacetime}" publish "$DB" --server "$HOST" --module-path "$HERE/server" \
  --delete-data=always --yes >/dev/null 2>&1 || fail "publish"

ORACLE=$(new_token); ALICE=$(new_token); BOB=$(new_token)

echo "oracle and accounts"
expect_err 'wrong oracle secret' "$ALICE" claim_oracle '["guess"]'
expect_ok "$ORACLE" claim_oracle "[\"$SECRET\"]"; pass "oracle claimed with secret"
expect_ok "$ALICE" register '["alice"]'
expect_ok "$BOB" register '["bob"]'; pass "alice and bob registered"
expect_err 'already registered' "$BOB" register '["bob2"]'
[[ $(balance_of alice) == $((1000 * MICRO)) ]] || fail "starting balance"
pass "starting balance 1000 credits"

echo "markets"
NOW=$(date +%s)
expect_err 'only an oracle' "$ALICE" create_market \
  "[\"sneaky\",\"lot-a\",\"car_count\",\">=\",40,$((NOW + 60)),100]"
expect_ok "$ORACLE" create_market \
  "[\"40+ cars in lot A at close?\",\"lot-a\",\"car_count\",\">=\",40,$((NOW + 6)),100]"
expect_ok "$ORACLE" create_market \
  "[\"150+ crossings per hour at crosswalk 1?\",\"crosswalk-1\",\"crossings_per_hour\",\">=\",150,$((NOW + 600)),100]"
SETTLE_ID=$(scalar "SELECT id FROM market WHERE zone = 'lot-a'")
VOID_ID=$(scalar "SELECT id FROM market WHERE zone = 'crosswalk-1'")
pass "created market $SETTLE_ID (to settle) and $VOID_ID (to void)"

echo "trading"
expect_ok "$ALICE" buy "[$SETTLE_ID,\"yes\",30]"
expect_ok "$BOB" buy "[$SETTLE_ID,\"no\",20]"
expect_ok "$ALICE" buy "[$VOID_ID,\"yes\",10]"
expect_ok "$BOB" buy "[$VOID_ID,\"no\",900]"
pass "4 trades placed"
expect_err 'not enough credits' "$BOB" buy "[$VOID_ID,\"no\",900]"
expect_err 'shares must be' "$BOB" buy "[$SETTLE_ID,\"yes\",0]"
expect_err "side must be" "$BOB" buy "[$SETTLE_ID,\"maybe\",1]"
sql "SELECT market_id, side, shares, cost_micro, price_yes_after FROM trade" | jq -r '.[] | "  trade market=\(.[0]) \(.[1]) x\(.[2]) cost=\(.[3] / 1000000) credits, P(yes) after=\(.[4] * 1000 | round / 10)%"'

echo "observations"
for v in 39 41 42 43; do
  expect_ok "$ORACLE" post_observation "[$NOW.5,\"lot-a\",\"car_count\",$v,0.8,\"stills/0001$v.jpg\"]"
done
expect_err 'only an oracle' "$BOB" post_observation "[$NOW,\"lot-a\",\"car_count\",99,0.9,\"x\"]"
expect_err 'confidence must be' "$ORACLE" post_observation "[$NOW,\"lot-a\",\"car_count\",1,1.5,\"x\"]"
pass "$(scalar 'SELECT COUNT(*) AS n FROM observation') observations stored"

echo "settlement"
expect_err 'not closed yet' "$ORACLE" settle "[$SETTLE_ID,42,\"too early\"]"
sleep $((NOW + 7 - $(date +%s)))
[[ $(scalar "SELECT status FROM market WHERE id = $SETTLE_ID") == closed ]] || fail "scheduled close"
pass "scheduled reducer closed market $SETTLE_ID at close_at"
expect_err 'market is closed' "$ALICE" buy "[$SETTLE_ID,\"yes\",1]"

BEFORE_A=$(balance_of alice); BEFORE_B=$(balance_of bob)
expect_ok "$ORACLE" settle "[$SETTLE_ID,42,\"Median of 4 frames within 60 s of close was 42 cars (conf 0.8), at or above 40.\"]"
expect_err 'already settled' "$ORACLE" settle "[$SETTLE_ID,10,\"again\"]"
[[ $(( $(balance_of alice) - BEFORE_A )) == $((30 * MICRO)) ]] || fail "alice YES payout"
[[ $(( $(balance_of bob) - BEFORE_B )) == 0 ]] || fail "bob NO gets nothing"
pass "settled YES at 42: alice +30 credits, bob +0"

expect_ok "$ORACLE" void_market "[$VOID_ID,\"Fewer than 3 frames with confidence >= 0.5 near close.\"]"
VOID_POOL=$(scalar "SELECT pool_micro FROM market WHERE id = $VOID_ID")
VOID_SUB=$(scalar "SELECT subsidy_micro FROM market WHERE id = $VOID_ID")
[[ $VOID_POOL == "$VOID_SUB" ]] || fail "void left pool $VOID_POOL != subsidy $VOID_SUB"
pass "voided market $VOID_ID: every stake refunded, pool back to subsidy"

echo "conservation"
BAL_SUM=$(sql 'SELECT balance_micro FROM account' | jq '[.[][0]] | add')
POOL_SUM=$(sql 'SELECT pool_micro FROM market' | jq '[.[][0]] | add')
SUB_SUM=$(sql 'SELECT subsidy_micro FROM market' | jq '[.[][0]] | add')
[[ $((BAL_SUM + POOL_SUM)) == $((2000 * MICRO + SUB_SUM)) ]] || fail "money created or destroyed"
pass "balances + pools = 2000 credits granted + subsidies ($BAL_SUM + $POOL_SUM = $((2000 * MICRO)) + $SUB_SUM micro)"
sql 'SELECT id, subsidy_micro, pool_micro FROM market' | jq -r '.[] | "  market \(.[0]): maker subsidy \(.[1] / 1000000) credits, pool left \(.[2] / 1000000), maker P&L \((.[2] - .[1]) / 1000000)"'
while read -r sub pool; do
  (( pool >= 0 )) || fail "pool went negative: maker lost more than its b*ln2 subsidy ($sub)"
done < <(sql 'SELECT subsidy_micro, pool_micro FROM market' | jq -r '.[] | "\(.[0]) \(.[1])"')
pass "no pool went negative, so the maker never lost more than b*ln2"
sql "SELECT name, balance_micro FROM account" | jq -r '.[] | "  \(.[0]): \(.[1] / 1000000) credits"'
echo "smoke test passed"
