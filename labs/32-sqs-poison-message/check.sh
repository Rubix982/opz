#!/usr/bin/env bash
# Runs a fresh emulator on port 9132, builds the queues with infra/queues.py,
# sends 12 good orders and 3 poison ones, and runs two workers for up to 45s.
# Passes only when: every good order ships exactly once, the poison messages end
# up in a dead-letter queue, the main queue drains, and monitor.py says OK on a
# healthy system but raises an ALARM once something is dead-lettered.
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (makes .venv)"; exit 1; }
export AWS_ENDPOINT_URL=http://localhost:9132
LEDGER="$(mktemp)"
fail=0

docker rm -f opz-lab32-check >/dev/null 2>&1
docker run -d --name opz-lab32-check -p 9132:5000 motoserver/moto:5.1.4 >/dev/null
w1=""; w2=""
trap 'kill $w1 $w2 2>/dev/null; docker rm -f opz-lab32-check >/dev/null 2>&1; rm -f "$LEDGER"' EXIT
for _ in $(seq 1 40); do curl -s localhost:9132 >/dev/null && break; sleep 0.5; done

$PY infra/queues.py >.check.log 2>&1 || { echo "FAIL  infra/queues.py crashed; see .check.log"; exit 1; }

if $PY app/monitor.py >>.check.log 2>&1; then echo "pass  monitor says OK on a healthy, empty system"
else echo "FAIL  monitor raises an alarm on a healthy, empty system"; fail=1; fi

$PY app/producer.py 12 3 >>.check.log 2>&1
$PY app/consumer.py "$LEDGER" w1 >>.check.log 2>&1 & w1=$!
$PY app/consumer.py "$LEDGER" w2 >>.check.log 2>&1 & w2=$!

# Wait until the main queue has been empty (nothing waiting, nothing in flight)
# for 3 polls in a row, or 45 seconds.
queue_state() {
  $PY - <<'PY'
import json, sys
sys.path.insert(0, "app")
from common import QUEUE, queue_url, sqs
c = sqs(); a = c.get_queue_attributes(QueueUrl=queue_url(QUEUE), AttributeNames=["All"])["Attributes"]
dlq_depth = -1
if "RedrivePolicy" in a:
    arn = json.loads(a["RedrivePolicy"])["deadLetterTargetArn"]
    d = c.get_queue_attributes(QueueUrl=c.get_queue_url(QueueName=arn.split(":")[-1])["QueueUrl"],
                               AttributeNames=["ApproximateNumberOfMessages"])["Attributes"]
    dlq_depth = int(d["ApproximateNumberOfMessages"])
print(int(a["ApproximateNumberOfMessages"]) + int(a["ApproximateNumberOfMessagesNotVisible"]), dlq_depth)
PY
}
echo "      running two workers (up to 45s)..."
empty=0
for _ in $(seq 1 45); do
  read -r left dlq < <(queue_state)
  if [ "$left" = 0 ]; then empty=$((empty + 1)); else empty=0; fi
  [ $empty -ge 3 ] && break
  sleep 1
done
kill $w1 $w2 2>/dev/null; wait $w1 $w2 2>/dev/null
read -r left dlq < <(queue_state)

shipped=$(sort "$LEDGER" | uniq | grep -c '^ord_')
total=$(grep -c '^ord_' "$LEDGER")
if [ "$shipped" = 12 ]; then echo "pass  all 12 good orders shipped"
else echo "FAIL  only $shipped of 12 good orders shipped"; fail=1; fi
if [ "$total" = "$shipped" ]; then echo "pass  no order shipped twice"
else echo "FAIL  $((total - shipped)) duplicate shipments: $(sort "$LEDGER" | uniq -d | head -3 | tr '\n' ' ')"; fail=1; fi

if [ "$dlq" = -1 ]; then echo "FAIL  the main queue has no dead-letter queue (no RedrivePolicy)"; fail=1
elif [ "$dlq" = 3 ]; then echo "pass  the 3 poison messages are in the dead-letter queue"
else echo "FAIL  dead-letter queue holds $dlq messages (expected the 3 poison ones)"; fail=1; fi

if [ "$left" = 0 ]; then echo "pass  main queue drained"
else echo "FAIL  main queue still holds $left messages after 45s (poison messages looping?)"; fail=1; fi

if $PY app/monitor.py >>.check.log 2>&1; then echo "FAIL  messages are dead-lettered and monitor still says OK"; fail=1
else echo "pass  monitor raises an ALARM once messages are dead-lettered"; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
