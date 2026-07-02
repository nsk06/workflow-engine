#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${API_URL:-http://localhost:18700}"

echo "==> Workflow Engine Demo"
echo ""

TOKEN=$("$ROOT/scripts/get-token.sh")
echo "Logged in as demo user"

echo "1) Submitting fanout workflow..."
RUN=$(curl -sf -X POST "$API/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"preset":"fanout"}')
RUN_ID=$(echo "$RUN" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "   run_id=$RUN_ID"

echo "2) Polling until complete..."
for i in $(seq 1 60); do
  STATUS=$(curl -sf "$API/runs/$RUN_ID" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "   status=$STATUS (attempt $i)"
  if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then
    break
  fi
  sleep 2
done

echo "3) Submitting flaky workflow..."
RUN2=$(curl -sf -X POST "$API/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"preset":"flaky"}')
RUN2_ID=$(echo "$RUN2" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "   run_id=$RUN2_ID"

echo "4) Cancelling second run..."
curl -sf -X POST "$API/runs/$RUN2_ID/cancel" -H "Authorization: Bearer $TOKEN" > /dev/null
echo "   cancelled"

echo ""
echo "==> Demo complete"
echo "UI:         http://localhost:18780"
echo "Prometheus: http://localhost:18790"
echo "Jaeger:     http://localhost:18786"
echo ""
echo "Scale workers: kubectl scale deployment workflow-worker -n workflow-system --replicas=8"
echo "Load test:     make loadtest"
