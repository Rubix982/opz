#!/usr/bin/env bash
# Builds a 5-node cluster from your node.py on the fake network in net.py, then
# partitions it in many shapes while clients read and write: minority sides,
# a 2-2-1 split, a node that missed everything, shifting partitions with lost
# messages, and links flapping every few milliseconds. Checks that minorities
# refuse, majorities keep working, nothing acknowledged is lost, and reads
# never go back in time. Each test runs in its own process with a deadline.
# Run one test: ./check.sh partition-shapes
cd "$(dirname "$0")" && exec python3 harness.py "$@"
