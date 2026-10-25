"""The on-call alarm for the order pipeline. Exit code 0 = OK, 1 = ALARM.

Run it on a schedule (or by hand): python app/monitor.py
"""

import sys

from common import QUEUE, queue_url, sqs

BACKLOG_LIMIT = 1000

client = sqs()
attrs = client.get_queue_attributes(QueueUrl=queue_url(QUEUE), AttributeNames=["ApproximateNumberOfMessages"])["Attributes"]
backlog = int(attrs["ApproximateNumberOfMessages"])

if backlog > BACKLOG_LIMIT:
    print(f"ALARM: {backlog} messages waiting")
    sys.exit(1)
print(f"OK: {backlog} messages waiting")
