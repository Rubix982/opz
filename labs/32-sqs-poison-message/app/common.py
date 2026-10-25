"""Shared settings. Everything talks to the local AWS emulator (moto), never real AWS."""

import os

import boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:9032")
QUEUE = "orders"
DLQ = "orders-dlq"


def sqs():
    return boto3.client(
        "sqs",
        endpoint_url=ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="FAKE_lab32_key",
        aws_secret_access_key="FAKE_lab32_secret",
    )


def queue_url(name: str) -> str:
    return sqs().get_queue_url(QueueName=name)["QueueUrl"]
