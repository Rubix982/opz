#!/usr/bin/env bash
# Destroys everything the lab made: the emulator holds the whole "account".
docker rm -f opz-lab33-moto opz-lab33-check >/dev/null 2>&1; echo "removed"
