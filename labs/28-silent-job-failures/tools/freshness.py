"""Freshness alert: is the last *successful* run recent enough?

    python tools/freshness.py [--status out/status.json] [--max-age-hours 26] [--now ISO-TIME]

Exits 0 if fresh, 1 if stale (this is what pages someone). --now lets check.sh
pretend it's a given time.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

p = argparse.ArgumentParser()
p.add_argument("--status", default="out/status.json")
p.add_argument("--max-age-hours", type=float, default=26)
p.add_argument("--now")
a = p.parse_args()

now = datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc)
try:
    last = json.load(open(a.status)).get("last_success")
except FileNotFoundError:
    last = None
if not last:
    print("STALE: no successful run recorded")
    sys.exit(1)
age_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600
if age_h > a.max_age_hours:
    print(f"STALE: last success {last}, {age_h:.1f}h ago (limit {a.max_age_hours:g}h)")
    sys.exit(1)
print(f"fresh: last success {last}, {age_h:.1f}h ago")
