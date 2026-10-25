#!/usr/bin/env bash
# Creates a local kind cluster "opz-lab35", builds and loads the image, and
# deploys the shop. Re-run to reset (it removes what you applied, then re-applies k8s/).
set -euo pipefail
cd "$(dirname "$0")"
CLUSTER=opz-lab35
kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"
kubectl config use-context "kind-$CLUSTER" >/dev/null
kubectl -n kube-system rollout status deployment/coredns --timeout=120s >/dev/null
docker build -q -t opz-lab35-app:1.0 app >/dev/null
kind load docker-image opz-lab35-app:1.0 --name "$CLUSTER"
# a clean slate: anything RBAC-ish left over from earlier attempts
kubectl delete clusterrolebinding -l opz-lab=35 --ignore-not-found >/dev/null
kubectl delete clusterrolebinding reporter-admin --ignore-not-found >/dev/null
kubectl delete namespace shop --ignore-not-found --wait=true >/dev/null
kubectl apply -f k8s/
kubectl -n shop rollout status deployment/reporter --timeout=90s
kubectl -n shop rollout status deployment/web --timeout=90s
echo "Deployed. Try: kubectl -n shop exec deploy/reporter -- python /app/peek.py"
