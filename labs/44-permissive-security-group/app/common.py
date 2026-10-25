"""Where the emulator is, and boto3 clients for EC2 and load balancers."""

import os

import boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:9044")


def client(service: str):
    # moto accepts any credentials; these are FAKE on purpose
    return boto3.client(
        service,
        endpoint_url=ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="FAKE",
        aws_secret_access_key="FAKE",
    )


def ec2():
    return client("ec2")


def elbv2():
    return client("elbv2")
