#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.env.ports" 2>/dev/null || true

API="${API_URL:-http://localhost:${API_PORT:-18700}}"
UI="${UI_URL:-http://localhost:${UI_PORT:-18780}}"
PROM="${PROMETHEUS_URL:-http://localhost:${PROMETHEUS_PORT:-18790}}"
GRAFANA="${GRAFANA_URL:-http://localhost:${GRAFANA_PORT:-18701}}"
JAEGER="${JAEGER_URL:-http://localhost:${JAEGER_PORT:-18786}}"
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "OK  $name"
  else
    echo "FAIL $name"
    FAIL=1
  fi
}

echo "==> E2E verification"
check "API health" "curl -sf $API/health"
check "API ready" "curl -sf $API/ready"
check "Prometheus" "curl -sf $PROM/-/healthy"
check "Grafana" "curl -sf $GRAFANA/api/health"
check "Jaeger" "curl -sf $JAEGER"
check "UI" "curl -sf $UI"

TOKEN=$(curl -sf -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"demo"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
check "Auth login" "test -n '$TOKEN'"

RUN=$(curl -sf -X POST "$API/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"preset":"linear"}')
RUN_ID=$(echo "$RUN" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
check "Submit workflow" "test -n '$RUN_ID'"

STATUS="running"
for i in $(seq 1 30); do
  STATUS=$(curl -sf "$API/runs/$RUN_ID" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  if [[ "$STATUS" == "completed" ]]; then
    echo "OK  Workflow completed"
    break
  fi
  sleep 1
done
[[ "$STATUS" == "completed" ]] || { echo "FAIL Workflow completion (status=$STATUS)"; FAIL=1; }

METRICS=$(curl -sf "$API/metrics" | grep -c workflow_ || true)
check "Prometheus metrics" "test ${METRICS:-0} -gt 0"

if [[ $FAIL -eq 0 ]]; then
  echo ""
  echo "All checks passed"
  echo "UI:         $UI"
  echo "API:        $API/docs"
  echo "Grafana:    $GRAFANA (admin/admin)"
  echo "Prometheus: $PROM"
  echo "Jaeger:     $JAEGER"
  exit 0
fi
exit 1
