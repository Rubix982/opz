"""Shared settings. Everything talks to the local AWS emulator (moto), never real AWS."""

import os

import boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:9033")


def ec2():
    return boto3.client(
        "ec2",
        endpoint_url=ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="FAKE_lab33_key",
        aws_secret_access_key="FAKE_lab33_secret",
    )
