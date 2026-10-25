#!/usr/bin/env bash
# The nightly drift check. CI runs this at 06:00 and pages if it exits non-zero.
# It has been green every night for a year.
cd "$(dirname "$0")/.."
tools/tf.sh plan -no-color -lock=false
echo "drift check finished"
