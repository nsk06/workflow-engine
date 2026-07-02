#!/usr/bin/env bash
set -euo pipefail
API="${API_URL:-http://localhost:18700}"

login() {
  local user="$1" pass="$2"
  curl -sf -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$user\",\"password\":\"$pass\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

submit() {
  local token="$1" preset="$2"
  curl -sf -X POST "$API/runs" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    -d "{\"preset\":\"$preset\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['run_id'][:8], d['status'])"
}

echo "==> Seeding workflows for demo, alice, bob"
for pair in "demo:demo:linear" "demo:demo:fanout" "alice:alice:fanout" "alice:alice:flaky" "bob:bob:linear" "bob:bob:fanout"; do
  IFS=: read -r user pass preset <<< "$pair"
  token=$(login "$user" "$pass")
  echo "  $user → $preset: $(submit "$token" "$preset")"
done

echo ""
echo "Done. Log in at http://localhost:18780 — each user sees only their runs."
echo "Grafana: http://localhost:18701/d/workflow-engine/workflow-engine (use User filter)"
