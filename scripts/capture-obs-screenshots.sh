#!/usr/bin/env bash
# Capture Grafana + Prometheus screenshots for docs (requires stack: make up).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.env.ports" 2>/dev/null || true
OUT="$ROOT/docs/e2e-screenshots"
GRAFANA_PORT="${GRAFANA_PORT:-18701}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-18790}"

mkdir -p "$OUT"
cd "$OUT"

PW="npx --yes playwright@1.49.0 screenshot --viewport-size=1440,900"

echo "==> Grafana dashboard (user=demo)"
$PW --wait-for-timeout=10000 \
  "http://localhost:${GRAFANA_PORT}/d/workflow-engine/workflow-engine?orgId=1&refresh=5s&var-user=demo" \
  05-grafana-dashboard-demo.png

echo "==> Prometheus targets"
$PW --wait-for-timeout=5000 \
  "http://localhost:${PROMETHEUS_PORT}/targets" \
  06-prometheus-targets.png

echo "==> Prometheus workflow_runs_submitted_total"
$PW --wait-for-timeout=8000 \
  "http://localhost:${PROMETHEUS_PORT}/graph?g0.expr=workflow_runs_submitted_total&g0.tab=0&g0.stacked=0&g0.range_input=15m" \
  07-prometheus-workflow-metrics.png

echo "==> Saved to docs/e2e-screenshots/05-07"
