# Lab 32 · Solution (spoilers)

## What was wrong

**Duplicates: visibility timeout shorter than the work.** A received message is
hidden for `VisibilityTimeout` seconds (1s here). An order of 3 takes 3 seconds
to ship. After 1 second the message reappears, the other worker takes it and
ships it again. Both workers then delete it, and the second delete is harmless,
so nothing ever complains.

**Poison messages looping: no dead-letter queue.** A malformed message fails
every time. The worker set its visibility to 0 ("retry right away"), so it
bounced between the workers thousands of times a minute, forever, burning CPU
and API calls (on real AWS you pay per request).

**A silent alarm.** `monitor.py` alarmed on more than 1,000 messages waiting.
Three stuck messages never get near that.

## The fix

`infra/queues.py`:

```python
dlq_url = client.create_queue(
    QueueName=DLQ,
    Attributes={"MessageRetentionPeriod": str(14 * 24 * 3600)},  # time to investigate
)["QueueUrl"]
dlq_arn = client.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]

client.create_queue(
    QueueName=QUEUE,
    Attributes={
        "VisibilityTimeout": "10",  # longer than the slowest message (3s), with room to spare
        "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}),
    },
)
```

`app/monitor.py` alarms when the dead-letter queue isn't empty:

```python
dlq = int(client.get_queue_attributes(QueueUrl=queue_url(DLQ),
          AttributeNames=["ApproximateNumberOfMessages"])["Attributes"]["ApproximateNumberOfMessages"])
if dlq > 0:
    print(f"ALARM: {dlq} message(s) in {DLQ}")
    sys.exit(1)
```

A DLQ without the alarm only turns "retrying forever" into "failing silently".
Somebody has to look at what lands there.

## Details worth knowing

- **Delete after success** gives *at-least-once* processing: if a worker dies
  mid-order, the message reappears and someone else finishes it. Deleting on
  receive gives *at-most-once*: a crash loses the order. For orders,
  at-least-once plus deduplication is the usual choice.
- **Even with the fix, duplicates can happen.** A worker can stall past 10
  seconds, or finish the work and die before the delete. Standard SQS also
  occasionally delivers twice by design. The real defence is an **idempotent
  consumer**: record `order_id` in a "shipped" table with a unique key and skip
  orders already there. (FIFO queues add deduplication within a 5-minute window.)
- **Long jobs** can extend their own timeout while they work
  (`ChangeMessageVisibility`, a "heartbeat"), instead of one huge timeout for every message.
- **Retry with backoff, not "right away".** Setting visibility to 0 on failure
  makes a hot loop. Leaving the timeout alone, or raising it on each retry, gives
  transient errors time to clear.
- **On real AWS** the better alarms are `ApproximateAgeOfOldestMessage`
  ("how late are we?") for latency and scaling, and DLQ depth > 0 for failures.
  Queue length says little without knowing how fast it's draining.
- **Redrive back.** Once the bug is fixed, `StartMessageMoveTask` moves messages
  from the DLQ back to the source queue.
