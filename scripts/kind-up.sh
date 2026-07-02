#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-workflow-demo}"

echo "==> Creating kind cluster: $CLUSTER_NAME"
kind create cluster --name "$CLUSTER_NAME" --config "$ROOT/scripts/kind-config.yaml" 2>/dev/null || \
  echo "Cluster may already exist"

echo "==> Installing ingress-nginx"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=120s

echo "==> Creating namespaces"
kubectl create namespace workflow-system --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace auth --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

echo "==> kind cluster ready"
