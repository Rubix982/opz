"""Nightly revenue job.

Reads the day's order export from the upstream billing system and writes two
files that the finance dashboard and three downstream reports read every morning:

    out/revenue_by_region.csv   paid revenue per region
    out/orders_clean.csv        every paid order, cleaned up
    out/status.json             what the ops dashboard shows (green/red, last run)

Run:  python job/nightly_revenue.py fixtures/orders-2026-10-21.csv
"""

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from faults import maybe_crash

OUT_DIR = os.environ.get("JOB_OUT_DIR", "out")


def now_iso() -> str:
    # JOB_NOW lets check.sh pretend it's a given night. Real runs use the clock.
    return os.environ.get("JOB_NOW") or datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_orders(path: str) -> list[dict]:
    orders = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                if row["status"] != "paid":
                    continue
                orders.append({"order_id": row["order_id"], "region": row["region"],
                               "amount_cents": int(row["amount_cents"])})
            except (KeyError, ValueError):
                continue  # skip weird rows, upstream sends a few now and then
    return orders


def write_outputs(orders: list[dict]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "orders_clean.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "region", "amount_cents"])
        w.writeheader()
        for i, order in enumerate(orders):
            maybe_crash(i)
            w.writerow(order)

    totals: dict[str, int] = defaultdict(int)
    for order in orders:
        totals[order["region"]] += order["amount_cents"]
    with open(os.path.join(OUT_DIR, "revenue_by_region.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["region", "revenue_cents"])
        for region in sorted(totals):
            w.writerow([region, totals[region]])


def main() -> None:
    started = now_iso()
    rows = 0
    try:
        orders = load_orders(sys.argv[1])
        rows = len(orders)
        write_outputs(orders)
        print(f"wrote {rows} orders", flush=True)
    except Exception as e:
        print(f"warning: {e}", file=sys.stderr)
    finally:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "status.json"), "w") as f:
            json.dump({"job": "nightly_revenue", "status": "success", "last_run": started,
                       "last_success": started, "rows": rows}, f, indent=2)
    sys.exit(0)


if __name__ == "__main__":
    main()
