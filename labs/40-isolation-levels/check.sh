#!/usr/bin/env bash
# Builds the current app/ as a separate stack on port 18040 and hammers it:
# many concurrent bookings for a few seats, and both doctors of a shift asking
# to go off call at once. Passes only when no event is oversold, every shift
# keeps a doctor on call, nobody gets a 500 (conflicts must be retried, not
# shown to users), and a busy round still finishes in reasonable time.
set -u
cd "$(dirname "$0")"
P="docker compose -p opz-lab40-check"
export APP_PORT=18040

$P up -d --build --wait >.check.log 2>&1 || { echo "stack didn't start; see .check.log"; exit 1; }
trap '$P down -v >/dev/null 2>&1' EXIT

python3 - <<'PY'
import sys, time
sys.path.insert(0, "tools")
from race import at_once, call

BASE = "http://127.0.0.1:18040"
ok = True
def report(passed, msg):
    global ok
    print(("pass  " if passed else "FAIL  ") + msg)
    ok = ok and passed

# 1. Bookings: 20 people, 5 seats, 10 times over.
oversold, errors, wrong_count, no_answer = [], 0, 0, 0
for t in range(10):
    call(BASE, "POST", "/reset?seats=5&events=1")
    codes = at_once(BASE, [f"/book?event=1&user=u{i}" for i in range(20)])
    ev = call(BASE, "GET", "/state")[1]["events"][0]
    errors += sum(c >= 500 for c in codes)
    no_answer += codes.count(0)
    if ev["bookings"] > 5:
        oversold.append(ev["bookings"])
    if codes.count(201) != ev["bookings"] or ev["seats_left"] != 5 - ev["bookings"]:
        wrong_count += 1
report(not oversold, "no event oversold (5 seats, 20 buyers, 10 trials)" if not oversold
       else f"oversold in {len(oversold)}/10 trials: {sorted(oversold)} bookings for 5 seats")
report(wrong_count == 0, "seats_left and bookings agree with what buyers were told" if wrong_count == 0
       else f"{wrong_count}/10 trials: seats_left, bookings and 201s disagree (lost update)")

# 2. Rota: both doctors of a shift go off call at once, 30 times.
empty, both_refused = 0, 0
for t in range(30):
    call(BASE, "POST", "/reset?shifts=1")
    codes = at_once(BASE, ["/off-call?doctor=alice-1", "/off-call?doctor=bob-1"])
    errors += sum(c >= 500 for c in codes)
    no_answer += codes.count(0)
    n = call(BASE, "GET", "/state")[1]["on_call_per_shift"]["1"]
    if n < 1:
        empty += 1
    elif sorted(codes) == [409, 409]:
        both_refused += 1
report(empty == 0, "every shift kept a doctor on call (30 trials)" if empty == 0
       else f"{empty}/30 trials left the shift with nobody on call (write skew)")
report(both_refused == 0, "one of the two always got to go off call" if both_refused == 0
       else f"{both_refused}/30 trials refused both doctors")

# 3. A busy round: 4 events x 25 seats, 120 buyers, all at once.
call(BASE, "POST", "/reset?seats=25&events=4")
start = time.time()
codes = at_once(BASE, [f"/book?event={i % 4 + 1}&user=b{i}" for i in range(120)])
took = time.time() - start
errors += sum(c >= 500 for c in codes)
no_answer += codes.count(0)
evs = call(BASE, "GET", "/state")[1]["events"]
total = sum(e["bookings"] for e in evs)
report(total == 100 and all(e["bookings"] == 25 for e in evs),
       "busy round: exactly 100 of 120 buyers booked" if total == 100
       else f"busy round: {total} bookings for 100 seats")
report(took < 15, f"busy round finished in {took:.1f}s" if took < 15
       else f"busy round took {took:.1f}s (everything serialized behind one lock?)")

report(errors == 0, "no 500s: conflicts were retried, not shown to users" if errors == 0
       else f"{errors} requests got a 500 (serialization failure or deadlock not retried?)")
report(no_answer == 0, "every request got an answer" if no_answer == 0
       else f"{no_answer} requests got no answer within 30s")
sys.exit(0 if ok else 1)
PY
rc=$?
[ "$rc" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $rc
