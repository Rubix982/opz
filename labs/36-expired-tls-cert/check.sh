#!/usr/bin/env bash
# Runs a separate copy of your lab (compose project opz-lab36-check, port 18436)
# with a fresh CA and the expired certificate, then checks:
#   1. monitor.sh pages for an expired and a short-lived cert, not for a healthy one
#   2. the expired cert is replaced automatically, and clients that trust only
#      the lab CA connect again
#   3. the served cert chains to the CA and has more than 30 days left
#   4. a short-lived cert is renewed automatically while requests keep flowing,
#      with none dropped
set -u
cd "$(dirname "$0")"
LAB=$PWD
CTX=$LAB/.check-ctx
P=opz-lab36-check
PORT=18436
MON_PORT=18437
fail=0

docker build -q -t opz-lab36-tools tools >/dev/null || { echo "tools image failed to build"; exit 1; }
rm -rf "$CTX"; mkdir -p "$CTX"
rsync -a --exclude .check-ctx --exclude pki --exclude .git ./ "$CTX/"
cd "$CTX"
tool() { docker run --rm -v "$CTX/$1:/pki" opz-lab36-tools "${@:2}"; }
dc() { HTTPS_PORT=$PORT docker compose -p $P "$@"; }
cleanup() {
  cd "$CTX" 2>/dev/null && dc down -v --remove-orphans >/dev/null 2>&1
  docker rm -f opz-lab36-check-mon >/dev/null 2>&1
  [ -n "${loop:-}" ] && kill "$loop" 2>/dev/null
}
trap cleanup EXIT

mkdir -p pki/live pki-mon/live
tool pki make-ca.sh /pki >/dev/null
cp -R pki/ca pki-mon/
export CA_FILE=$CTX/pki/ca/ca.crt

# 1. The monitor, against a throwaway TLS server whose certificate we control.
monitor_on() {  # validity -> exit code of monitor.sh against it
  docker rm -f opz-lab36-check-mon >/dev/null 2>&1
  tool pki-mon issue.sh /pki "$1" >/dev/null
  docker run -d --name opz-lab36-check-mon -p 127.0.0.1:$MON_PORT:8443 -v "$CTX/pki-mon:/pki:ro" \
    opz-lab36-tools openssl s_server -accept 8443 -cert /pki/live/tls.crt -key /pki/live/tls.key -www -quiet >/dev/null
  for _ in $(seq 1 20); do nc -z 127.0.0.1 $MON_PORT 2>/dev/null && break; sleep 0.3; done
  ./monitor.sh localhost:$MON_PORT >/dev/null 2>&1; echo $?
}
[ "$(monitor_on expired)" != 0 ] && echo "pass  monitor pages for an expired certificate" \
  || { echo "FAIL  monitor says OK for an expired certificate"; fail=1; }
[ "$(monitor_on 2d)" != 0 ] && echo "pass  monitor warns about a certificate with 2 days left" \
  || { echo "FAIL  monitor says OK for a certificate with 2 days left"; fail=1; }
[ "$(monitor_on 90d)" = 0 ] && echo "pass  monitor is quiet for a healthy 90-day certificate" \
  || { echo "FAIL  monitor pages for a healthy 90-day certificate"; fail=1; }
docker rm -f opz-lab36-check-mon >/dev/null 2>&1

# 2. The frontend starts with last year's expired certificate. Does anything fix it?
tool pki issue.sh /pki expired >/dev/null
dc up -d --build >"$LAB/.check.log" 2>&1 || { echo "FAIL  docker compose up failed; see .check.log"; echo "lab not passed yet"; exit 1; }
ok=no
for _ in $(seq 1 60); do
  curl -fs --cacert "$CA_FILE" "https://localhost:$PORT/" >/dev/null 2>&1 && { ok=yes; break; }; sleep 1
done
[ $ok = yes ] && echo "pass  expired certificate replaced automatically; clients trusting the lab CA connect" \
  || { echo "FAIL  after 60s clients trusting the lab CA still can't connect (not renewed, or not issued by the lab CA)"; fail=1; }

served_ok() {  # served cert chains to the CA and has more than 30 days left
  local pem; pem=$(mktemp)
  openssl s_client -connect localhost:$PORT -servername localhost </dev/null 2>/dev/null | openssl x509 >"$pem" 2>/dev/null
  openssl verify -CAfile "$CA_FILE" "$pem" >/dev/null 2>&1 && openssl x509 -in "$pem" -noout -checkend $((30 * 86400)) >/dev/null 2>&1
  local rc=$?; rm -f "$pem"; return $rc
}
served_ok && echo "pass  served certificate chains to the lab CA with more than 30 days left" \
  || { echo "FAIL  served certificate doesn't chain to the CA or has 30 days or less left"; fail=1; }

# 3. A short-lived certificate goes in while traffic flows. It must be renewed
#    automatically, and no request may fail across the swap.
stats=$(mktemp)
python3 - "$PORT" "$CA_FILE" "$stats" <<'PY' & loop=$!
import ssl, sys, time, urllib.request, os, signal
port, ca, out = sys.argv[1], sys.argv[2], sys.argv[3]
ctx = ssl.create_default_context(cafile=ca)
ok = bad = 0
stop = False
def done(*_):
    global stop; stop = True
signal.signal(signal.SIGTERM, done)
while not stop:
    try:
        urllib.request.urlopen(f"https://localhost:{port}/", context=ctx, timeout=3).read(); ok += 1
    except Exception:
        bad += 1
    with open(out, "w") as f: f.write(f"{ok} {bad}")
    time.sleep(0.1)
PY
sleep 2
tool pki issue.sh /pki 120s >/dev/null
renewed=no
for _ in $(seq 1 60); do sleep 1; served_ok && { renewed=yes; break; }; done
sleep 2; kill $loop 2>/dev/null; wait $loop 2>/dev/null; loop=
read -r ok bad <"$stats"; rm -f "$stats"
[ $renewed = yes ] && echo "pass  short-lived certificate renewed automatically" \
  || { echo "FAIL  a certificate with 2 minutes left wasn't replaced by a CA-issued one with 30+ days within 60s"; fail=1; }
if [ "${ok:-0}" -gt 20 ] && [ "${bad:-1}" = 0 ]; then echo "pass  no requests dropped across the swap ($ok answered)"
else echo "FAIL  requests failed during the swap: ${bad:-?} of $(( ${ok:-0} + ${bad:-0} ))"; fail=1; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
