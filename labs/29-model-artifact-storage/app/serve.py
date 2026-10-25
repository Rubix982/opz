"""The inference server's startup: fetch the weights and load them.

    python app/serve.py load sentiment/v3

Exits 0 and prints the weights' SHA-256 when the model loaded; nonzero if it
refused to load.
"""

import hashlib
import sys

from common import BUCKET, client, model_key


def load_model(name: str) -> bytes:
    s3 = client("server")
    weights = s3.get_object(Bucket=BUCKET, Key=model_key(name))["Body"].read()
    # (a real server would now deserialize the weights and start serving)
    return weights


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "load":
        sys.exit(__doc__)
    weights = load_model(sys.argv[2])
    print(f"loaded {sys.argv[2]}: {len(weights)} bytes, sha256 {hashlib.sha256(weights).hexdigest()}")
