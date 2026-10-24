#!/usr/bin/env bash
# Deploys Balloon Patrol to the development environment, installs it on the demo site for Jira and
# Confluence, and writes the station's credentials to ~/.config/balloon/forge.json (mode 600).
# Run after `forge register` has put the app id in manifest.yml. Never prints the secret.
set -euo pipefail

SITE="${SITE:-one-atlas-dqcx.atlassian.net}"
ENVIRONMENT="${ENVIRONMENT:-development}"
CONF_DIR="$HOME/.config/balloon"
CONF="$CONF_DIR/forge.json"
cd "$(dirname "$0")/.."

grep -q '^  id: ari:cloud:ecosystem::app/' manifest.yml || { echo "No app id in manifest.yml. Run: forge register balloon-patrol" >&2; exit 1; }

pnpm install --silent

mkdir -p "$CONF_DIR" && chmod 700 "$CONF_DIR"
SECRET="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("secret",""))' "$CONF" 2>/dev/null || true)"
[ -n "$SECRET" ] || SECRET="$(openssl rand -hex 32)"

forge variables set -e "$ENVIRONMENT" --encrypt INGEST_SECRET "$SECRET" >/dev/null
echo "INGEST_SECRET set (encrypted) for $ENVIRONMENT"

forge deploy --non-interactive -e "$ENVIRONMENT"

for product in jira confluence; do
  if forge install list -e "$ENVIRONMENT" 2>/dev/null | grep -i "$SITE" | grep -qi "$product"; then
    forge install --upgrade --non-interactive --confirm-scopes --site "$SITE" --product "$product" -e "$ENVIRONMENT"
  else
    forge install --non-interactive --confirm-scopes --site "$SITE" --product "$product" -e "$ENVIRONMENT"
  fi
done

URL="$(forge webtrigger create -f ingest-alert --site "$SITE" --product jira -e "$ENVIRONMENT" 2>&1 | grep -Eo 'https://[^[:space:]]+' | tail -1)"
[ -n "$URL" ] || { echo "Couldn't read the web trigger URL; run: forge webtrigger create -f ingest-alert" >&2; exit 1; }

SECRET="$SECRET" URL="$URL" SITE="$SITE" python3 - "$CONF" <<'PY'
import json, os, sys
path = sys.argv[1]
data = {"webtrigger_url": os.environ["URL"], "secret": os.environ["SECRET"], "header": "X-Balloon-Secret", "site": os.environ["SITE"]}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump(data, f, indent=2)
os.chmod(path, 0o600)
PY
echo "Station credentials written to $CONF (mode 600)"
