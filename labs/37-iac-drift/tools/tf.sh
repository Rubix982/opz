#!/usr/bin/env bash
# Runs Terraform from a pinned Docker image (nothing installed on your machine),
# on the lab's compose network so it can reach the emulator as http://aws:5000.
#   tools/tf.sh plan
#   TF_DIR=/some/other/dir COMPOSE_PROJECT=opz-lab37-check tools/tf.sh apply -auto-approve
set -euo pipefail
LAB="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${TF_DIR:-$LAB/infra}"
NET="${COMPOSE_PROJECT:-opz-lab37}_default"
mkdir -p "$LAB/.tf-cache"
exec docker run --rm -i \
  --network "$NET" \
  -v "$DIR":/work -w /work \
  -v "$LAB/.tf-cache":/tf-cache -e TF_PLUGIN_CACHE_DIR=/tf-cache \
  -e TF_IN_AUTOMATION=1 -e TF_INPUT=0 \
  hashicorp/terraform:1.9.8 "$@"
