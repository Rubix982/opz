#!/usr/bin/env bash
# Deletes the emulator, and with it every queue and message.
docker rm -f opz-lab32-moto opz-lab32-check >/dev/null 2>&1; echo "removed"
