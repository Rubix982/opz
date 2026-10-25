"""Fire concurrent requests at the clinic API and show what happened.

    python3 tools/race.py book            # 20 people try to book 5 seats at once
    python3 tools/race.py off-call        # alice and bob both ask to go off call at once
    python3 tools/race.py book --base http://127.0.0.1:18040 --trials 10

Standard library only.
"""

import argparse
import json
import threading
import urllib.error
import urllib.request
from collections import Counter


def call(base: str, method: str, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(base + path, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0, {}  # no answer at all


def at_once(base: str, paths: list[str]) -> list[int]:
    codes: list[int] = [0] * len(paths)
    start = threading.Barrier(len(paths))

    def go(i: int, p: str) -> None:
        start.wait()
        codes[i] = call(base, "POST", p)[0]

    threads = [threading.Thread(target=go, args=(i, p)) for i, p in enumerate(paths)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return codes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["book", "off-call"])
    ap.add_argument("--base", default="http://127.0.0.1:8040")
    ap.add_argument("--trials", type=int, default=1)
    args = ap.parse_args()
    for t in range(args.trials):
        if args.what == "book":
            call(args.base, "POST", "/reset?seats=5&events=1")
            codes = at_once(args.base, [f"/book?event=1&user=u{i}" for i in range(20)])
        else:
            call(args.base, "POST", "/reset?shifts=1")
            codes = at_once(args.base, ["/off-call?doctor=alice-1", "/off-call?doctor=bob-1"])
        st = call(args.base, "GET", "/state")[1]
        print(f"trial {t + 1}: responses {dict(Counter(codes))}  state {json.dumps(st)}")


if __name__ == "__main__":
    main()
