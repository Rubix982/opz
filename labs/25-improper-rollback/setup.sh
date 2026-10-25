#!/usr/bin/env bash
# Puts v2 live (as a plain copy in models/current/), the state before the incident.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf models/current
mkdir -p models/current
cp models/v2/*.json models/current/
echo "v2 is live. Start the service: python3 app.py"
