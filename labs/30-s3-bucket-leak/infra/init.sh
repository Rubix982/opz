#!/usr/bin/env bash
# Sets up the exports bucket. Runs once each time the stack starts.
set -euo pipefail
mc() { /opt/bitnami/minio-client/bin/mc --quiet "$@"; }

mc alias set local http://s3:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing local/acme-customer-exports
mc cp /sample/*.csv local/acme-customer-exports/2026/ >/dev/null

# 2026-03: Partner (Brightline) needs the Q1 export for the demo, and their
# tooling can't do AWS auth. Opening it up for the demo -- remember to close
# this afterwards!  -- j.
mc anonymous set public local/acme-customer-exports
