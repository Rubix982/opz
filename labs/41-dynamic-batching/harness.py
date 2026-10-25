"""Test harness for lab 41. Run through ./check.sh.

Each test runs in its own subprocess with a deadline, so a batcher that hangs
shows up as a FAIL line instead of freezing the terminal. The load test also
runs a one-request-per-call baseline on the same model and writes both sets of
numbers to results.txt.
"""

import os
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class Fail(Exception):
    pass


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]


def start_all(threads: list[threading.Thread], deadline: float) -> None:
    for t in threads:
        t.daemon = True
        t.start()
    end = time.monotonic() + deadline
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
        if t.is_alive():
            raise Fail(f"callers still waiting after {deadline:.0f}s (lost request or deadlock?)")


def make(model, **kw):
    from batcher import Batcher

    opts = {"max_batch_size": 16, "max_wait_ms": 5.0, "max_queue": 256}
    opts.update(kw)
    return Batcher(model, **opts)


# ---------------------------------------------------------------- tests


def test_basics() -> str:
    from model import Model, expected

    m = Model()
    b = make(m)
    try:
        for word in ["kettle", "teapot", "kettle", "mug"]:
            got = b.submit(word)
            if got != expected(word):
                raise Fail(f"submit({word!r}) returned {got!r}, the model says {expected(word)!r}")
    finally:
        b.close()
    return "single requests come back with the right answer"


def test_routing() -> str:
    from model import Model, expected

    m = Model()
    b = make(m)
    wrong: list[str] = []
    errors: list[str] = []

    def caller(n: int) -> None:
        for i in range(25):
            item = f"user{n}-req{i}"
            try:
                got = b.submit(item)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{item}: {type(e).__name__}: {e}")
                return
            if got != expected(item):
                wrong.append(item)

    try:
        start_all([threading.Thread(target=caller, args=(n,)) for n in range(48)], 40)
    finally:
        b.close()
    if errors:
        raise Fail(f"{len(errors)} requests raised, e.g. {errors[0]}")
    if wrong:
        raise Fail(f"{len(wrong)} of 1200 callers got someone else's answer (e.g. {wrong[0]})")
    if max(m.batch_sizes) < 2:
        raise Fail("every model call had one item: nothing was batched")
    if max(m.batch_sizes) > 16:
        raise Fail(f"a batch of {max(m.batch_sizes)} items exceeded max_batch_size=16")
    avg = m.items / m.calls
    return f"1200 requests from 48 threads, each got its own answer (avg batch {avg:.1f}, max {max(m.batch_sizes)})"


def test_bad_item() -> str:
    from model import BadInput, Model, expected

    m = Model()
    b = make(m)
    problems: list[str] = []

    def caller(item: str) -> None:
        try:
            got = b.submit(item)
        except BadInput:
            if not item.startswith("!"):
                problems.append(f"good item {item!r} failed because of a bad neighbour")
            return
        except Exception as e:  # noqa: BLE001
            problems.append(f"{item!r} raised {type(e).__name__}: {e}")
            return
        if item.startswith("!"):
            problems.append(f"bad item {item!r} returned {got!r} instead of raising BadInput")
        elif got != expected(item):
            problems.append(f"{item!r} got someone else's answer")

    try:
        for rnd in range(3):
            items = [f"r{rnd}-ok{i}" for i in range(20)]
            for j in (3, 11, 17):
                items[j] = f"!r{rnd}-bad{j}"
            barrier = threading.Barrier(len(items))

            def go(it: str) -> None:
                barrier.wait()
                caller(it)

            start_all([threading.Thread(target=go, args=(it,)) for it in items], 20)
    finally:
        b.close()
    if problems:
        raise Fail(f"{len(problems)} problems, e.g. {problems[0]}")
    if max(m.batch_sizes) < 2:
        raise Fail("never batched: bad items were only isolated because nothing was batched")
    return "3 bad items per wave: their callers get BadInput, the other 17 get their answers"


def run_load(submit, users: int, per_user: int) -> tuple[float, list[float]]:
    lat: list[float] = []
    lock = threading.Lock()
    errors: list[str] = []
    barrier = threading.Barrier(users)

    def user(n: int) -> None:
        barrier.wait()
        for i in range(per_user):
            t0 = time.perf_counter()
            try:
                submit(f"load-u{n}-{i}")
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
                return
            with lock:
                lat.append(time.perf_counter() - t0)

    t0 = time.perf_counter()
    start_all([threading.Thread(target=user, args=(n,)) for n in range(users)], 60)
    wall = time.perf_counter() - t0
    if errors:
        raise Fail(f"{len(errors)} requests failed under load, e.g. {errors[0]}")
    return len(lat) / wall, lat


def test_load() -> str:
    from model import Model

    base_model = Model()
    base_rps, base_lat = run_load(lambda x: base_model.predict([x])[0], 10, 20)

    m = Model()
    b = make(m)
    try:
        rps, lat = run_load(b.submit, 10, 20)
    finally:
        b.close()

    lines = [
        "Load test, 10 concurrent users x 20 requests, same model",
        f"one request per call : {base_rps:7.1f} req/s   p95 {p95(base_lat) * 1000:6.1f} ms",
        f"dynamic batching     : {rps:7.1f} req/s   p95 {p95(lat) * 1000:6.1f} ms   (avg batch {m.items / m.calls:.1f})",
    ]
    with open(os.path.join(HERE, "results.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    if rps < 2.5 * base_rps:
        raise Fail(f"{rps:.0f} req/s is not 2.5x the one-at-a-time {base_rps:.0f} req/s")
    if p95(lat) >= p95(base_lat):
        raise Fail(f"p95 {p95(lat) * 1000:.0f} ms isn't lower than one-at-a-time {p95(base_lat) * 1000:.0f} ms")
    return (f"10 users: {rps:.0f} req/s vs {base_rps:.0f}, p95 {p95(lat) * 1000:.0f} ms vs "
            f"{p95(base_lat) * 1000:.0f} ms (saved to results.txt)")


def test_low_load() -> str:
    from model import Model

    base_model = Model()
    _, base_lat = run_load(lambda x: base_model.predict([x])[0], 1, 40)
    m = Model()
    b = make(m)
    try:
        _, lat = run_load(b.submit, 1, 40)
    finally:
        b.close()
    limit = p95(base_lat) + 0.030
    if p95(lat) > limit:
        raise Fail(f"a lone user waits {p95(lat) * 1000:.0f} ms at p95 vs {p95(base_lat) * 1000:.0f} ms "
                   f"unbatched; with max_wait_ms=5 it should be under {limit * 1000:.0f} ms "
                   f"(is the batch waiting to fill up?)")
    return f"one user alone: p95 {p95(lat) * 1000:.0f} ms vs {p95(base_lat) * 1000:.0f} ms unbatched"


def test_backpressure() -> str:
    from batcher import QueueFull
    from model import Model, expected

    m = Model(overhead_s=0.2)
    b = make(m, max_batch_size=4, max_queue=8)
    peak = 0
    stop = threading.Event()
    rejected: list[float] = []
    answered = 0
    problems: list[str] = []
    lock = threading.Lock()

    def sampler() -> None:
        nonlocal peak
        while not stop.is_set():
            peak = max(peak, b.pending())
            time.sleep(0.002)

    barrier = threading.Barrier(60)

    def caller(n: int) -> None:
        nonlocal answered
        item = f"bp{n}"
        barrier.wait()
        t0 = time.perf_counter()
        try:
            got = b.submit(item, timeout=30)
        except QueueFull:
            with lock:
                rejected.append(time.perf_counter() - t0)
            return
        except Exception as e:  # noqa: BLE001
            problems.append(f"{type(e).__name__}: {e}")
            return
        if got != expected(item):
            problems.append(f"{item} got the wrong answer")
        with lock:
            answered += 1

    s = threading.Thread(target=sampler, daemon=True)
    s.start()
    try:
        start_all([threading.Thread(target=caller, args=(n,)) for n in range(60)], 40)
    finally:
        stop.set()
        b.close()
    if problems:
        raise Fail(f"{len(problems)} problems, e.g. {problems[0]}")
    if not rejected:
        raise Fail("60 callers hit a queue of 8 with a slow model and none got QueueFull (unbounded queue?)")
    if peak > 8:
        raise Fail(f"pending() reached {peak}, above max_queue=8")
    slow = [r for r in rejected if r > 0.1]
    if slow:
        raise Fail(f"{len(slow)} rejections took over 100 ms; QueueFull should be immediate, not after waiting")
    if answered + len(rejected) != 60:
        raise Fail(f"{answered} answered + {len(rejected)} rejected != 60 callers")
    return f"queue of 8 under a flood: {len(rejected)} rejected at once, {answered} answered, peak pending {peak}"


def test_shutdown() -> str:
    from batcher import Closed
    from model import Model, expected

    before = threading.active_count()
    m = Model()
    b = make(m)
    results: dict[str, str] = {}
    closed: list[str] = []
    problems: list[str] = []

    def caller(n: int) -> None:
        item = f"sd{n}"
        try:
            results[item] = b.submit(item, timeout=20)
        except Closed:
            closed.append(item)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{item}: {type(e).__name__}: {e}")

    threads = [threading.Thread(target=caller, args=(n,), daemon=True) for n in range(40)]
    for t in threads:
        t.start()
    time.sleep(0.01)
    t0 = time.perf_counter()
    b.close()
    took = time.perf_counter() - t0
    for t in threads:
        t.join(20)
    if any(t.is_alive() for t in threads):
        raise Fail("some callers were never answered after close()")
    if problems:
        raise Fail(f"{len(problems)} callers failed, e.g. {problems[0]}")
    bad = [k for k, v in results.items() if v != expected(k)]
    if bad:
        raise Fail(f"{len(bad)} callers got the wrong answer around close()")
    if took > 5:
        raise Fail(f"close() took {took:.1f}s")
    try:
        b.submit("after-close", timeout=2)
        raise Fail("submit() after close() didn't raise Closed")
    except Closed:
        pass
    time.sleep(0.1)
    if threading.active_count() > before:
        raise Fail("a worker thread is still running after close()")
    return f"close() finished {len(results)} accepted requests, refused {len(closed)}, worker stopped"


TESTS = [
    ("basics", test_basics),
    ("routing", test_routing),
    ("bad-item", test_bad_item),
    ("load", test_load),
    ("low-load", test_low_load),
    ("backpressure", test_backpressure),
    ("shutdown", test_shutdown),
]


def run_one(name: str) -> int:
    fn = dict(TESTS)[name]
    try:
        print(fn())
        return 0
    except NotImplementedError:
        print("not implemented yet")
        return 1
    except Fail as e:
        print(e)
        return 1
    except Exception:  # noqa: BLE001
        print("crashed: " + traceback.format_exc().strip().splitlines()[-1])
        return 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--one":
        return run_one(sys.argv[2])
    failed = 0
    for name, _ in TESTS:
        try:
            r = subprocess.run([sys.executable, __file__, "--one", name], capture_output=True,
                               text=True, timeout=90)
            msg = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:] or "no output"])[-1]
            ok = r.returncode == 0
        except subprocess.TimeoutExpired:
            msg, ok = "hung for 90s (deadlock, or a caller never answered?)", False
        print(f"{'pass' if ok else 'FAIL'}  {name:12} {msg}")
        failed += not ok
    print("LAB PASSED" if failed == 0 else "lab not passed yet")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
