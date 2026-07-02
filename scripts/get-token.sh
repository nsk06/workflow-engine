#!/usr/bin/env bash
set -euo pipefail
API="${API_URL:-http://localhost:18700}"
USERNAME="${DEMO_USER:-demo}"
PASSWORD="${DEMO_PASS:-demo}"

curl -sf -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
