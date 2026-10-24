#!/usr/bin/env bash
# Fills a database with demo markets, trades, balloon counts and one settled market, so the page has
# something to show before the station is running. Usage: ORACLE_SECRET=... scripts/seed-demo.sh
set -euo pipefail

HOST="${SPACETIME_HOST:-http://127.0.0.1:3000}"
DB="${SPACETIME_DB:-balloon-market}"
: "${ORACLE_SECRET:?set ORACLE_SECRET to the secret the module was published with}"
source "$(dirname "$0")/lib.sh"

must() { local res; res=$(call "$@"); [[ $res == 200* ]] || { echo "$2 failed: $res"; exit 1; }; }

ORACLE=$(new_token); MAYA=$(new_token); DEV=$(new_token)
must "$ORACLE" claim_oracle "[\"$ORACLE_SECRET\"]"
must "$MAYA" register '["maya"]'
must "$DEV" register '["dev"]'

NOW=$(date +%s)
must "$ORACLE" create_market "[\"40 or more cars in lot A at close?\",\"lot-a\",\"car_count\",\">=\",40,$((NOW + 1800)),100,\"Lot A has held 35 to 42 cars all afternoon, so 40 is close to a coin flip.\"]"
must "$ORACLE" create_market "[\"More than 150 people cross crosswalk 1 per hour?\",\"crosswalk-1\",\"crossings_per_hour\",\">\",150,$((NOW + 3600)),100,\"Crossings have run 120 to 140 per hour since noon; a ferry arrival could push it over.\"]"
must "$ORACLE" create_market "[\"Lot B under 20 cars at close?\",\"lot-b\",\"car_count\",\"<\",20,$((NOW + 6)),50,\"Lot B usually empties after 2 PM.\"]"

LOT_A=$(scalar "SELECT id FROM market WHERE zone = 'lot-a'")
CROSS=$(scalar "SELECT id FROM market WHERE zone = 'crosswalk-1'")
LOT_B=$(scalar "SELECT id FROM market WHERE zone = 'lot-b'")
must "$MAYA" buy "[$LOT_A,\"yes\",40]"
must "$DEV" buy "[$LOT_A,\"no\",15]"
must "$DEV" buy "[$CROSS,\"yes\",25]"
must "$MAYA" buy "[$LOT_B,\"no\",20]"

must "$ORACLE" post_observation "[$NOW,\"lot-a\",\"car_count\",37,0.86,\"stills/000456.jpg\"]"
must "$ORACLE" post_observation "[$NOW,\"crosswalk-1\",\"crossings_per_hour\",132,0.72,\"stills/000456.jpg\"]"
must "$ORACLE" post_observation "[$NOW,\"lot-b\",\"car_count\",23,0.9,\"stills/000456.jpg\"]"

sleep 7
must "$ORACLE" settle "[$LOT_B,23,\"Median of 28 frames within 60 s of close was 23 cars, all with confidence of at least 0.8. 23 is not under 20, so NO.\"]"
echo "seeded $DB: 3 markets (1 settled), 4 trades, 3 live counts"
