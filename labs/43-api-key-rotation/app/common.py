"""Shared settings: where the emulator is, and the boto3 client for API Gateway."""

import os
from pathlib import Path

import boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:9043")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8043")
KEYS_DIR = Path(os.environ.get("KEYS_DIR", Path(__file__).resolve().parent.parent / "keys"))
CLIENTS = ["billing", "reports", "mobile"]
PLAN_NAME = "partners"


def apigw():
    # moto accepts any credentials; these are FAKE on purpose
    return boto3.client(
        "apigateway",
        endpoint_url=ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="FAKE",
        aws_secret_access_key="FAKE",
    )


def plan_id(ag) -> str:
    for p in ag.get_usage_plans()["items"]:
        if p["name"] == PLAN_NAME:
            return p["id"]
    raise SystemExit(f"usage plan {PLAN_NAME!r} not found: run ./setup.sh")


def keys_for(ag, client: str) -> list[dict]:
    """Every API key tagged for this client, with values, oldest first."""
    items = ag.get_api_keys(includeValues=True)["items"]
    mine = [k for k in items if (k.get("tags") or {}).get("client") == client]
    return sorted(mine, key=lambda k: k["createdDate"])
