#!/usr/bin/env bash
# Puts v2 live with ./deploy.sh v2, starts the service on port 18025, sends
# steady traffic, and rolls back with ./deploy.sh v1 in the middle. ~5 seconds.
set -u
cd "$(dirname "$0")"
python3 harness.py
rc=$?
[ "$rc" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $rc
