#!/usr/bin/env bash
# Imports buffer.py and attacks it with threads: FIFO and timeouts, a long
# many-producer/many-consumer stress run, close() semantics, CPU use while
# blocked, and transfers between two accounts in both directions at once.
# Each test runs in its own process with a deadline, so a deadlock is a FAIL, not a hang.
cd "$(dirname "$0")" && exec python3 harness.py
