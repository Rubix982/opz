#!/usr/bin/env bash
# Imports batcher.py and tests it against model.py: every caller gets its own
# answer, one bad input doesn't sink its batch, throughput and p95 at ten users
# beat one-request-per-call (numbers saved to results.txt), a lone user isn't
# kept waiting, the queue is bounded, and close() is clean.
# Each test runs in its own process with a deadline, so a hang is a FAIL.
cd "$(dirname "$0")" && exec python3 harness.py
