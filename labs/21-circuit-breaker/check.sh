#!/usr/bin/env bash
# Imports breaker.py, gives it a fake clock, and runs it against a dependency
# that is healthy, then failing or slow, then healthy again: thresholds, fast
# refusals while open, a single half-open trial, 50 callers at once, recovery.
cd "$(dirname "$0")" && exec python3 harness.py
