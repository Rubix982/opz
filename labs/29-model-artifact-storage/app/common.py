"""Shared S3 client setup. Each service passes its own config file."""

import os
from pathlib import Path

import boto3
from botocore.config import Config

LAB = Path(__file__).resolve().parent.parent
BUCKET = "models"
ENDPOINT = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:9029")


def read_env_file(path: Path) -> dict[str, str]:
    pairs = (l.split("=", 1) for l in path.read_text().splitlines() if "=" in l and not l.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


def client(config_name: str):
    """config_name: "trainer" or "server" -> reads config/<name>.env"""
    creds = read_env_file(LAB / "config" / f"{config_name}.env")
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=creds["S3_ACCESS_KEY"],
        aws_secret_access_key=creds["S3_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def model_key(name: str) -> str:
    return f"{name}/model.bin"
