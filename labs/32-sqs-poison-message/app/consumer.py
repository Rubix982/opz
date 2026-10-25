"""Order worker. Takes one message at a time, ships the order, deletes the message.

    python app/consumer.py [ledger=shipped.log] [name=worker]

Every shipment is appended to the ledger file, one order_id per line. In real
life that line is a parcel leaving the warehouse.
"""

import json
import sys
import time

from common import QUEUE, queue_url, sqs

SECONDS_PER_ITEM = 1.0  # the warehouse API is slow, and slower for bigger orders
ledger = sys.argv[1] if len(sys.argv) > 1 else "shipped.log"
name = sys.argv[2] if len(sys.argv) > 2 else "worker"
client, url = sqs(), queue_url(QUEUE)


def ship(body: str) -> str:
    order = json.loads(body)  # poison messages fail here...
    qty = int(order["qty"])   # ...or here
    time.sleep(SECONDS_PER_ITEM * qty)  # 1-3 seconds
    with open(ledger, "a") as f:
        f.write(f"{order['order_id']}\n")
    return f"{order['order_id']} x{qty}"


while True:
    resp = client.receive_message(QueueUrl=url, MaxNumberOfMessages=1, WaitTimeSeconds=1)
    for msg in resp.get("Messages", []):
        try:
            print(f"[{name}] shipped {ship(msg['Body'])}", flush=True)
            client.delete_message(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"])
        except Exception as e:
            print(f"[{name}] failed: {e!r}; retrying right away", flush=True)
            client.change_message_visibility(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"], VisibilityTimeout=0)
