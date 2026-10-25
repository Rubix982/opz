"""What the ops dashboard shows for the job. Usage: python tools/dashboard.py [out/status.json]"""

import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "out/status.json"
s = json.load(open(path))
light = "\033[32mGREEN\033[0m" if s.get("status") == "success" else "\033[31mRED\033[0m"
print(f"{s.get('job')}: {light}  last run {s.get('last_run')}  last success {s.get('last_success')}  rows {s.get('rows')}")
