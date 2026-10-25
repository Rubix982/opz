#!/usr/bin/env bash
# Plays a week of nights against the job in a scratch output folder:
# a good night, then an empty export, a corrupted one, one where upstream
# renamed a column, and a crash mid-write. Passes only when every bad night is
# reported as failed, leaves the last good output byte-for-byte untouched, makes
# the freshness alert fire, and a good night afterwards still works.
set -u
cd "$(dirname "$0")"
PY=python3
F=fixtures
export JOB_OUT_DIR="$(mktemp -d)"
trap 'rm -rf "$JOB_OUT_DIR" "$SNAP"' EXIT
SNAP="$(mktemp -d)"
fail=0
: > .check.log

run() {  # now, input, [extra env...] -> sets $code
  local now=$1 input=$2; shift 2
  env JOB_NOW="$now" "$@" $PY job/nightly_revenue.py "$input" >>.check.log 2>&1; code=$?
}
expected_totals() {  # input -> "region,cents" lines for paid orders
  $PY - "$1" <<'PY'
import csv, sys
from collections import defaultdict
t = defaultdict(int)
for r in csv.DictReader(open(sys.argv[1])):
    if r["status"] == "paid": t[r["region"]] += int(r["amount_cents"])
for k in sorted(t): print(f"{k},{t[k]}")
PY
}
status_field() { $PY -c "import json,sys; print(json.load(open('$JOB_OUT_DIR/status.json')).get('$1'))" 2>/dev/null; }
same_as_snapshot() { cmp -s "$JOB_OUT_DIR/orders_clean.csv" "$SNAP/orders_clean.csv" && cmp -s "$JOB_OUT_DIR/revenue_by_region.csv" "$SNAP/revenue_by_region.csv"; }

# Night 1: a normal export.
run 2026-10-21T02:00:00+00:00 $F/orders-2026-10-21.csv
got=$(tail -n +2 "$JOB_OUT_DIR/revenue_by_region.csv" 2>/dev/null | tr -d "\r")
if [ "$code" = 0 ] && [ "$got" = "$(expected_totals $F/orders-2026-10-21.csv)" ]; then echo "pass  good night: exit 0, totals correct"
else echo "FAIL  good night: exit $code, totals wrong or missing"; fail=1; fi
cp "$JOB_OUT_DIR"/orders_clean.csv "$JOB_OUT_DIR"/revenue_by_region.csv "$SNAP"/ 2>/dev/null

# Nights 2-5: things go wrong.
bad_night() {  # label, input, [env...]
  local label=$1 input=$2; shift 2
  run 2026-10-22T02:00:00+00:00 "$input" "$@"
  local problems=()
  [ "$code" = 0 ] && problems+=("exited 0")
  same_as_snapshot || problems+=("last good output was changed")
  [ "$(status_field status)" = success ] && problems+=("dashboard says success")
  if [ ${#problems[@]} = 0 ]; then printf 'pass  %-26s failed loudly (exit %s), good output untouched\n' "$label" "$code"
  else printf 'FAIL  %-26s %s\n' "$label" "$(IFS=';'; echo "${problems[*]}" | sed 's/;/; /g')"; fail=1; fi
}
bad_night "empty export"            $F/orders-2026-10-22-empty.csv
bad_night "corrupted amounts"       $F/orders-2026-10-22-corrupt.csv
bad_night "upstream renamed column" $F/orders-2026-10-22-renamed.csv
bad_night "crash mid-write"         $F/orders-2026-10-20.csv JOB_CRASH_AFTER_ROWS=100

# Morning after: the freshness alert should fire (last success was 28h ago).
if $PY tools/freshness.py --status "$JOB_OUT_DIR/status.json" --now 2026-10-22T06:00:00+00:00 >>.check.log 2>&1
then echo "FAIL  freshness alert silent 28h after the last good run"; fail=1
else echo "pass  freshness alert fires 28h after the last good run"; fi

# Upstream fixed, re-run: everything goes back to green.
run 2026-10-22T07:00:00+00:00 $F/orders-2026-10-20.csv
got=$(tail -n +2 "$JOB_OUT_DIR/revenue_by_region.csv" 2>/dev/null | tr -d "\r")
if [ "$code" = 0 ] && [ "$got" = "$(expected_totals $F/orders-2026-10-20.csv)" ] \
   && $PY tools/freshness.py --status "$JOB_OUT_DIR/status.json" --now 2026-10-22T08:00:00+00:00 >>.check.log 2>&1
then echo "pass  recovery run: exit 0, new totals, alert clears"
else echo "FAIL  recovery run didn't succeed cleanly (exit $code)"; fail=1; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
