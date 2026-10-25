"""Creates the order queue. Our stand-in for the Terraform that defines it.

Run it again after changing it: it deletes and recreates the queues, so start
from an empty system each time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from common import DLQ, QUEUE, sqs  # noqa: E402

client = sqs()
for name in (QUEUE, DLQ):
    try:
        client.delete_queue(QueueUrl=client.get_queue_url(QueueName=name)["QueueUrl"])
    except client.exceptions.QueueDoesNotExist:
        pass

client.create_queue(
    QueueName=QUEUE,
    Attributes={
        "VisibilityTimeout": "1",  # seconds
    },
)
print(f"created queue {QUEUE}")
