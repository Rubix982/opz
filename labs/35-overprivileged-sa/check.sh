#!/usr/bin/env bash
# Checks the live cluster (./setup.sh first, then kubectl apply your fix).
# Passes only when, using the reporter pod's OWN token, Secrets and cluster-wide
# reads are refused while its ConfigMap still reads fine; kubectl auth can-i
# agrees; the app is still doing its job; and the web pod has no token at all.
set -u
cd "$(dirname "$0")"
K="kubectl --context kind-opz-lab35"
SA="system:serviceaccount:shop:reporter"
fail=0

$K -n shop get deploy reporter >/dev/null 2>&1 || { echo "no reporter deployment: run ./setup.sh"; exit 1; }
$K -n shop rollout status deploy/reporter --timeout=90s >/dev/null 2>&1
$K -n shop rollout status deploy/web --timeout=90s >/dev/null 2>&1

# 1. The pod's own token, from inside the pod.
probes=$($K -n shop exec deploy/reporter -- python /app/peek.py --json 2>/dev/null)
if [ -z "$probes" ]; then echo "FAIL  couldn't run peek.py in the reporter pod"; echo "lab not passed yet"; exit 1; fi
status_of() { python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(next((r['status'] for r in d.get('results',[]) if r['probe']==sys.argv[2]), 'none'))" "$probes" "$1"; }

c=$(status_of "own ConfigMap (the app's real job)")
if [ "$c" = 200 ]; then echo "pass  pod token: reads its own ConfigMap"
else echo "FAIL  pod token: can't read its own ConfigMap (got $c): the app is broken"; fail=1; fi
for p in "list Secrets in shop" "read a Secret in billing" "list namespaces (cluster-wide)" "list pods in every namespace"; do
  c=$(status_of "$p")
  if [ "$c" = 403 ]; then printf 'pass  pod token: %-32s refused (403)\n' "$p"
  else printf 'FAIL  pod token: %-32s got %s (should be 403)\n' "$p" "$c"; fail=1; fi
done

# 2. kubectl auth can-i, asking as the service account.
can() { $K auth can-i "$@" --as="$SA" 2>/dev/null; }
for q in "get secrets -n shop" "list secrets -n billing" "list pods --all-namespaces" "create deployments -n shop" "update configmaps/reporter-config -n shop"; do
  if [ "$(can $q)" = no ]; then printf 'pass  can-i %-40s no\n' "$q"
  else printf 'FAIL  can-i %-40s yes\n' "$q"; fail=1; fi
done

# 3. The app still does its job: it read its config within the last 10 seconds.
st=$($K -n shop exec deploy/reporter -- python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/status').read().decode())" 2>/dev/null)
if python3 -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if d['ok'] and d['seconds_since_read'] is not None and d['seconds_since_read'] < 10 else 1)" "$st" 2>/dev/null
then echo "pass  reporter is reading its config (status ok)"
else echo "FAIL  reporter isn't reading its config: ${st:-no answer}"; fail=1; fi

# 4. Pods that never call the API carry no token.
if $K -n shop exec deploy/web -- ls /var/run/secrets/kubernetes.io/serviceaccount/token >/dev/null 2>&1
then echo "FAIL  web pod has a service account token mounted, and never uses it"; fail=1
else echo "pass  web pod has no token mounted"; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
