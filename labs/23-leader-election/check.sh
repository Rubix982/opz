#!/usr/bin/env bash
# Runs clusters of three of your nodes against a lease coordinator and a fenced
# storage, kills the leader, and freezes leaders mid-write. ~25 seconds.
set -u
cd "$(dirname "$0")"
python3 harness.py
rc=$?
[ "$rc" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $rc
