"""check.sh's harness: roll back v2 -> v1 with ./deploy.sh while the service is under load."""

import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 18025
URL = f"http://127.0.0.1:{PORT}/predict"
failures = 0


def report(ok: bool, msg: str) -> None:
    global failures
    print(("pass  " if ok else "FAIL  ") + msg, flush=True)
    failures += 0 if ok else 1


def expected_score(version: str, x: list[float]) -> float:
    d = HERE / "models" / version
    pre = json.loads((d / "preprocess.json").read_text())
    wts = json.loads((d / "weights.json").read_text())
    z = [(xi - mu) / s for xi, mu, s in zip(x, pre["mean"], pre["scale"])]
    return wts["bias"] + sum(c * zi for c, zi in zip(wts["coef"], z))


def post(x: list[float]) -> tuple[int, dict]:
    req = urllib.request.Request(URL, data=json.dumps({"x": x}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def main() -> int:
    rng = random.Random(25)
    inputs = [[rng.uniform(-2, 2) for _ in range(600)] for _ in range(5)]
    expect = {v: [expected_score(v, x) for x in inputs] for v in ("v1", "v2")}

    d = subprocess.run(["./deploy.sh", "v2"], cwd=HERE, capture_output=True, text=True)
    if d.returncode != 0:
        report(False, f"./deploy.sh v2 failed: {(d.stderr or d.stdout).strip()[-200:]}")
        return 1

    log_path = HERE / ".check.log"
    log = open(log_path, "w")
    srv = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                           env={**os.environ, "PORT": str(PORT)})
    try:
        for _ in range(100):
            if post(inputs[0])[0] == 200:
                break
            time.sleep(0.05)

        results: list[tuple[float, int, int, dict]] = []
        stop = threading.Event()

        def load(offset: int) -> None:
            i = offset
            while not stop.is_set():
                code, body = post(inputs[i % 5])
                results.append((time.monotonic(), i % 5, code, body))
                i += 1

        threads = [threading.Thread(target=load, args=(k,)) for k in range(4)]
        for t in threads:
            t.start()
        time.sleep(1.0)
        rb = subprocess.run(["./deploy.sh", "v1"], cwd=HERE, capture_output=True, text=True)
        rolled_back_at = time.monotonic()
        time.sleep(1.5)
        stop.set()
        for t in threads:
            t.join()
    finally:
        srv.terminate()
        srv.wait()
        log.close()

    if rb.returncode != 0:
        report(False, f"./deploy.sh v1 failed: {(rb.stderr or rb.stdout).strip()[-200:]}")
        return 1

    def which(i: int, body: dict) -> str | None:
        s = body.get("score")
        if s is None:
            return None
        for v in ("v1", "v2"):
            if abs(s - expect[v][i]) < 1e-4:
                return v
        return "mixed"

    failed = [r for r in results if r[2] != 200]
    mixed = [r for r in results if r[2] == 200 and which(r[1], r[3]) == "mixed"]
    after = [which(r[1], r[3]) for r in results if r[0] > rolled_back_at + 0.5]
    print(f"      {len(results)} requests during the rollback", flush=True)
    report(not failed, f"no failed requests ({len(failed)} failed)")
    report(not mixed, f"every answer came from one complete version ({len(mixed)} came from a mix of v1 and v2 files)")
    report(bool(after) and all(v == "v1" for v in after), "after the rollback, every answer is v1")

    lines = [l for l in log_path.read_text().splitlines() if l.startswith("predict")]
    versions = [next((p.split("=", 1)[1] for p in l.split() if p.startswith("version=")), None) for l in lines]
    tagged = all(versions) and bool(versions)
    switches = sum(1 for a, b in zip(versions, versions[1:]) if a != b)
    report(tagged, "every request log line names the model version that served it"
           + ("" if tagged else f" ({versions.count(None)} of {len(versions)} lines don't)"))
    report(tagged and switches == 1 and versions[0] == "v2" and versions[-1] == "v1",
           "the log shows one clean switch from v2 to v1"
           + ("" if not tagged else f" (switched {switches} times)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
