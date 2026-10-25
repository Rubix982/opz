#!/usr/bin/env bash
# Starts the local AWS emulator, applies infra/ with Terraform, then replays the
# hand changes made during last night's incident. Re-run to reset everything
# (the emulator starts empty and the local state is thrown away).
set -euo pipefail
cd "$(dirname "$0")"
docker compose down -v >/dev/null 2>&1 || true
rm -f infra/terraform.tfstate infra/terraform.tfstate.backup
docker compose up -d --wait
tools/tf.sh init -no-color >/dev/null
tools/tf.sh apply -auto-approve -no-color | tail -1
tools/incident.sh
echo "Ready. Start with: tools/drift-check.sh; echo exit=\$?"
