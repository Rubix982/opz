#!/usr/bin/env bash
# Deletes the emulator (and the secret in it). Stop db/server.py with Ctrl-C.
docker rm -f opz-lab34-moto opz-lab34-check >/dev/null 2>&1; echo "removed"
