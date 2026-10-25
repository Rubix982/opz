"""The three client services, as threads, each calling GET /orders ~5 times a second.

Each one reads its key from keys/<name>.key before every request, the way a
service re-reads a mounted secret. Prints a line per second per client.

    python app/clients.py                      # all three, until Ctrl-C
    python app/clients.py --sticky reports     # "reports" reads its key once at
                                               # startup and never again (a
                                               # client nobody remembered to update)
    python app/clients.py --ledger out.tsv --duration 30
"""

import argparse
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

from common import CLIENTS, GATEWAY_URL, KEYS_DIR

counts = {c: Counter() for c in CLIENTS}
lock = threading.Lock()


def call(key: str) -> int:
    req = urllib.request.Request(f"{GATEWAY_URL}/orders", headers={"x-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0  # gateway unreachable


def run(name: str, sticky: bool, ledger, stop: threading.Event) -> None:
    key = (KEYS_DIR / f"{name}.key").read_text().strip()
    while not stop.is_set():
        if not sticky:
            key = (KEYS_DIR / f"{name}.key").read_text().strip()
        status = call(key)
        with lock:
            counts[name][status] += 1
            if ledger:
                ledger.write(f"{time.time():.3f}\t{name}\t{status}\n")
                ledger.flush()
        time.sleep(0.2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sticky", action="append", default=[])
    ap.add_argument("--ledger")
    ap.add_argument("--duration", type=float, default=0)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    ledger = open(args.ledger, "a") if args.ledger else None
    stop = threading.Event()
    threads = [threading.Thread(target=run, args=(c, c in args.sticky, ledger, stop), daemon=True) for c in CLIENTS]
    for t in threads:
        t.start()
    start = time.time()
    try:
        while not args.duration or time.time() - start < args.duration:
            time.sleep(1)
            if not args.quiet:
                with lock:
                    line = "  ".join(
                        f"{c}: {counts[c][200]} ok {counts[c][403]} denied" for c in CLIENTS
                    )
                print(line, flush=True)
    except KeyboardInterrupt:
        pass
    stop.set()


if __name__ == "__main__":
    main()
