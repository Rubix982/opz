#!/usr/bin/env bash
# Checks the decision record: decision.json names a real variant that meets every
# hard constraint in data/benchmarks.csv, isn't beaten on every axis by another
# feasible option (unless DECISION.md says why not), and quotes its numbers
# correctly; DECISION.md has every section written, states the targets, compares
# at least two options with numbers; the revisit triggers are measurable.
cd "$(dirname "$0")" && exec python3 check.py
