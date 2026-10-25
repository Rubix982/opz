#!/usr/bin/env bash
# Starts your server.py in a fresh process per test and attacks it over real
# sockets: requests split byte by byte, pipelining, 40 clients at once, malformed
# and oversized requests, clients that trickle bytes forever, 40 idle
# connections, and a shutdown in the middle of a request.
# A test that hangs is killed at its deadline and counts as a FAIL.
# Run one test: ./check.sh slowloris
cd "$(dirname "$0")" && exec python3 harness.py "$@"
