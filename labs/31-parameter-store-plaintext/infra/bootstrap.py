"""Puts the orders service's config into Parameter Store, then prepares the
app's environment. Run by setup.sh against the local AWS emulator.

    AWS_ENDPOINT_URL=http://127.0.0.1:9031 python infra/bootstrap.py
"""

import json
import os
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://127.0.0.1:9031")

ssm = boto3.client("ssm", endpoint_url=ENDPOINT, region_name="us-east-1",
                   aws_access_key_id="testing", aws_secret_access_key="testing")

seed = {k: v for k, v in json.loads((HERE / "seed.json").read_text()).items() if not k.startswith("_")}

for name, value in seed.items():
    ssm.put_parameter(Name=name, Value=value, Type="String", Overwrite=True)
    print(f"put {name} = {value}")

# The container can't call Parameter Store itself yet, so hand it the values.
env_lines = [f"{name.rsplit('/', 1)[1].upper()}={value}" for name, value in seed.items()]
(HERE.parent / ".env.app").write_text("\n".join(env_lines) + "\n")
print("wrote .env.app for the app container")
