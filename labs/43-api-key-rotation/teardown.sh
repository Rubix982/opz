#!/usr/bin/env bash
# Deletes the emulator (and with it every key) and the handed-out key files.
cd "$(dirname "$0")"
docker rm -f opz-lab43-moto opz-lab43-check >/dev/null 2>&1; rm -rf keys; echo "removed"
