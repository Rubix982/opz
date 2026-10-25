#!/usr/bin/env bash
# Sets up the model store. Runs each time the stack starts.
set -euo pipefail
mc() { /opt/bitnami/minio-client/bin/mc --quiet "$@"; }

mc alias set local http://s3:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing local/models

# The inference boxes pull weights at boot and managing keys on them was a pain,
# so the bucket is readable without credentials. It's internal anyway.
mc anonymous set download local/models

# Seed: the model currently in production.
head -c 300000 /dev/urandom > /tmp/model.bin
mc cp /tmp/model.bin local/models/sentiment/v3/model.bin >/dev/null
echo "model store ready"
