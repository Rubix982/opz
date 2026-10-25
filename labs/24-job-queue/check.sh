#!/usr/bin/env bash
# Unit checks on your queue, then a chaos run: 4 worker processes, 80 jobs,
# 3 poison jobs, workers SIGKILLed at random and all at once. ~15-30 seconds.
set -u
cd "$(dirname "$0")"
python3 harness.py
rc=$?
[ "$rc" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $rc
