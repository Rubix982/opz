"""The training job's last step: publish the weights.

    python app/train.py publish sentiment/v4 path/to/model.bin
"""

import sys
from pathlib import Path

from common import BUCKET, client, model_key


def publish(name: str, weights: Path) -> None:
    s3 = client("trainer")
    s3.put_object(Bucket=BUCKET, Key=model_key(name), Body=weights.read_bytes())
    print(f"published {name} ({weights.stat().st_size} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "publish":
        sys.exit(__doc__)
    publish(sys.argv[2], Path(sys.argv[3]))
