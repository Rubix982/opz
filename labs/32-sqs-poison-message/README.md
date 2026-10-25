# Lab 32 · SQS Message Flood Unprocessed, Causes Latency

**Time:** ~45 min · **Needs:** Docker, Python 3 · **Cost:** free. Runs against a
local AWS emulator, not a real account.

## The incident

The order pipeline is an SQS queue with two workers. Since a partner started
sending orders, three things have been going wrong:

- Some customers got **two parcels** for one order.
- The workers' logs are a wall of `failed: ...; retrying right away`, thousands a
  minute, from a handful of malformed messages.
- The queue never quite empties, and the on-call alarm has never fired once.

## About the emulator

Everything runs against [moto](https://github.com/getmoto/moto), a local fake of
the AWS APIs, in a Docker container on `localhost:9032`. The code uses ordinary
`boto3` calls, the same ones you'd make against real SQS. Only the
`endpoint_url` differs. What's different from real AWS:

- moto doesn't publish **CloudWatch metrics** for SQS. On AWS you'd alarm on
  `ApproximateAgeOfOldestMessage` and on the DLQ's
  `ApproximateNumberOfMessagesVisible`. Here `app/monitor.py` reads the queue
  attributes directly instead.
- Credentials are FAKE; moto accepts anything.

## Setup

```bash
./setup.sh                       # emulator + .venv + the queue (infra/queues.py)
source .venv/bin/activate
python app/producer.py           # 12 good orders + 3 malformed ones
python app/consumer.py shipped.log w1 &   # two workers sharing a ledger
python app/consumer.py shipped.log w2 &
sort shipped.log | uniq -d       # orders shipped more than once
python app/monitor.py            # what on-call sees
kill %1 %2
```

Re-run `python infra/queues.py` to wipe and recreate the queues. Delete
`shipped.log` between runs.

## Your job

1. **Explain each symptom** before changing anything. Hints, one at a time:
   - When a worker receives a message, it's hidden from other workers for the
     queue's *visibility timeout*. What's that timeout, and how long does
     `ship()` take for an order of 3?
   - What happens to a message that fails? Look at the `except` branch, then at
     what's missing from `infra/queues.py`.
   - `ApproximateReceiveCount`: every receive counts. What should happen at, say,
     the third failure?
   - `monitor.py` alarms on queue *length*. Would 3 stuck messages ever trip it?
     What would actually tell you something is wrong?
2. **Fix it**: mostly in `infra/queues.py` (the queue's settings) and
   `app/monitor.py`. The consumer's basic shape, deleting only after success, is
   right; work out why that's the safe order.
3. **Prove it.** `./check.sh` uses its own emulator (port 9132), so it won't touch
   your queues. It sends 12 orders and 3 poison messages through two workers and
   passes only when every order ships exactly once, the poison messages are
   parked in a dead-letter queue, the main queue drains, and the monitor is
   quiet on a healthy system but alarms on dead letters.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why orders shipped twice (the timeline, in two lines):
- What a dead-letter queue is, and what `maxReceiveCount` decides:
- Why "delete after success" and not "delete on receive":
- Why queue length is a poor alarm, and what to alarm on instead:
- What still allows a duplicate even after the fix (and the real defence):
