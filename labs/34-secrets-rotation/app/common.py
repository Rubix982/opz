"""Shared settings. Secrets live in the local AWS emulator (moto), never real AWS."""

import json
import os
import urllib.error
import urllib.request

import boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:9034")
DB_URL = os.environ.get("DB_URL", "http://localhost:8034")
SECRET_ID = "orders/db"
DB_ADMIN_TOKEN = os.environ.get("DB_ADMIN_TOKEN", "admin_FAKE_lab34_do_not_use")


def secrets():
    return boto3.client(
        "secretsmanager",
        endpoint_url=ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="FAKE_lab34_key",
        aws_secret_access_key="FAKE_lab34_secret",
    )


def db_post(path: str, body: dict, admin: bool = False) -> int:
    """POST to the database; returns the HTTP status (raises only if it can't connect)."""
    headers = {"Content-Type": "application/json"}
    if admin:
        headers["X-Admin-Token"] = DB_ADMIN_TOKEN
    req = urllib.request.Request(DB_URL + path, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def can_login(password: str) -> bool:
    return db_post("/login", {"user": "app", "password": password}) == 200
