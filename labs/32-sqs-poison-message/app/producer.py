"""Sends orders to the queue: N good ones plus a few malformed ("poison") ones.

    python app/producer.py [good=12] [poison=3]
"""

import json
import sys

from common import QUEUE, queue_url, sqs

good = int(sys.argv[1]) if len(sys.argv) > 1 else 12
poison = int(sys.argv[2]) if len(sys.argv) > 2 else 3
client, url = sqs(), queue_url(QUEUE)

for i in range(good):
    client.send_message(QueueUrl=url, MessageBody=json.dumps({"order_id": f"ord_{i:03d}", "qty": 1 + i % 3}))
# Bad data from a partner's integration: quantity isn't a number, or not even JSON.
for i in range(poison):
    body = json.dumps({"order_id": f"bad_{i}", "qty": "lots"}) if i % 2 == 0 else "<order>oops</order>"
    client.send_message(QueueUrl=url, MessageBody=body)
print(f"sent {good} orders and {poison} malformed ones")
