#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-workflow-demo}"

echo "==> Building images"
docker build -t workflow-engine:latest "$ROOT/backend"
docker build -t workflow-ui:latest \
  --build-arg VITE_API_URL=/api \
  "$ROOT/frontend"

echo "==> Loading images into kind"
kind load docker-image workflow-engine:latest --name "$CLUSTER_NAME"
kind load docker-image workflow-ui:latest --name "$CLUSTER_NAME"

echo "==> Deploying workflow stack"
kubectl apply -f "$ROOT/k8s/manifests/workflow.yaml"

echo "==> Waiting for deployments"
kubectl rollout status deployment/workflow-api -n workflow-system --timeout=120s || true
kubectl rollout status deployment/workflow-worker -n workflow-system --timeout=120s || true
kubectl rollout status deployment/workflow-ui -n workflow-system --timeout=120s || true

echo "==> Deploy complete"
echo "UI:  http://localhost/"
echo "API: http://localhost/api/health"
