# Shared curl helpers for the market's HTTP API. Source after setting HOST and DB.

new_token() { curl -sf -X POST "$HOST/v1/identity" | jq -r .token; }

# call TOKEN REDUCER JSON_ARGS -> prints "HTTP_CODE BODY"
call() {
  local out code
  out=$(curl -s -w '\n%{http_code}' -X POST "$HOST/v1/database/$DB/call/$2" \
    -H "Authorization: Bearer $1" -H 'Content-Type: application/json' -d "$3")
  code=$(tail -n1 <<<"$out")
  printf '%s %s' "$code" "$(sed '$d' <<<"$out")"
}

sql() { curl -sf -X POST "$HOST/v1/database/$DB/sql" -d "$1" | jq -c '.[0].rows'; }
scalar() { sql "$1" | jq -r '.[0][0]'; }
