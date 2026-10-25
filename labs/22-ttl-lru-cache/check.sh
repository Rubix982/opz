#!/usr/bin/env bash
# Imports cache.py, gives it a fake clock, and tests expiry (to the exact
# boundary), LRU order, dropping expired entries before live ones, memory not
# growing with dead entries, 100,000 operations under a time limit, stats, and
# 8 threads hammering it at once.
cd "$(dirname "$0")" && exec python3 harness.py
