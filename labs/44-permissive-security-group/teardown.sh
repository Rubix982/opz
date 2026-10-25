#!/usr/bin/env bash
# Deletes the emulator, and with it the whole network.
docker rm -f opz-lab44-moto opz-lab44-check >/dev/null 2>&1; echo "removed"
