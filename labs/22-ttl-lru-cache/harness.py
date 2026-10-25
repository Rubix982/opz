"""Test harness for lab 22. Run through ./check.sh.

The cache gets a fake clock the harness moves by hand. Each test runs in its
own subprocess with a deadline.
"""

import os
import random
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Fail(Exception):
    pass


class FakeClock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


MISS = object()


def make(capacity: int, ttl: float):
    from cache import TTLCache

    clock = FakeClock()
    return TTLCache(capacity, ttl, clock=clock), clock


def present(c, key) -> bool:
    return c.get(key, MISS) is not MISS


# ---------------------------------------------------------------- tests


def test_basics() -> str:
    c, _ = make(10, 60)
    c.set("a", 1)
    c.set("b", 2)
    if c.get("a") != 1 or c.get("b") != 2:
        raise Fail("get() didn't return what set() stored")
    if c.get("zzz", "dflt") != "dflt":
        raise Fail("get() of a missing key didn't return the default")
    c.set("a", 10)
    if c.get("a") != 10:
        raise Fail("set() on an existing key didn't replace the value")
    if len(c) != 2:
        raise Fail(f"len is {len(c)} with 2 keys stored")
    return "set, get, default, overwrite, len"


def test_expiry() -> str:
    c, clock = make(10, 60)
    c.set("a", 1)
    c.set("short", 2, ttl=5)
    clock.advance(4.999)
    if c.get("short") != 2:
        raise Fail("an entry expired before its ttl")
    clock.advance(0.001)
    if present(c, "short"):
        raise Fail("an entry was returned at exactly set-time + ttl (it has expired)")
    clock.advance(55)
    if present(c, "a"):
        raise Fail("an entry was returned after its ttl")
    c.set("a", 3)
    clock.advance(59)
    if c.get("a") != 3:
        raise Fail("set() on an existing key didn't restart its ttl")
    return "never returns an expired entry (including at the exact boundary); set() restarts the ttl"


def test_lru() -> str:
    c, _ = make(3, 60)
    for k in "abc":
        c.set(k, k)
    c.get("a")            # a is now most recently used: order b, c, a
    c.set("d", "d")       # evicts b
    if present(c, "b"):
        raise Fail("evicted the wrong entry: b was least recently used and is still there")
    if not all(present(c, k) for k in "acd"):
        raise Fail("evicted an entry that was used more recently than b")
    c.set("c", "c2")      # overwrite counts as use: order a, d, c  (get above reordered too)
    c.get("d")
    c.set("e", "e")       # least recently used is now a
    if present(c, "a") or not all(present(c, k) for k in "cde"):
        raise Fail("set() on an existing key or get() didn't update recency")
    if len(c) > 3:
        raise Fail(f"holds {len(c)} entries, capacity is 3")
    return "evicts the least recently used; get() and overwrites count as use"


def test_expired_first() -> str:
    c, clock = make(3, 100)
    c.set("short", 1, ttl=1)
    c.set("b", 2)
    c.set("c", 3)
    c.get("short")        # short is most recently used, but about to expire
    clock.advance(2)
    c.set("d", 4)         # full: the expired entry must go, not b
    if not present(c, "b"):
        raise Fail("evicted a live entry (b) while an expired one was taking up space")
    if not all(present(c, k) for k in "cd"):
        raise Fail("lost a live entry")
    return "makes room by dropping expired entries before evicting live ones"


def test_no_lingering() -> str:
    c, clock = make(1000, 1)
    for i in range(1000):
        c.set(i, i, ttl=1 + (i % 3))
    clock.advance(2.5)  # ttl 1 and 2 have expired; ttl 3 hasn't
    c.set("new", 1)
    live = sum(1 for i in range(1000) if i % 3 == 2)
    if len(c) != live + 1:
        raise Fail(f"after a set(), {len(c)} entries held; {live + 1} are live (expired entries linger in memory)")
    clock.advance(10)
    c.set("newer", 1)
    if len(c) != 1:
        raise Fail(f"everything but one key has expired, yet {len(c)} entries are held after a set()")
    return "expired entries leave memory, not just stop being returned"


def test_overload() -> str:
    rng = random.Random(22)
    cap = 5000
    c, clock = make(cap, 3)
    truth: dict[int, tuple[int, float]] = {}  # key -> (value, expires_at)
    ops = 100_000
    t0 = time.monotonic()
    for n in range(ops):
        clock.advance(0.0005)
        k = rng.randrange(40_000)
        if rng.random() < 0.6:
            ttl = rng.choice((5, 10, 30, 60))
            c.set(k, n, ttl=ttl)
            truth[k] = (n, clock.now + ttl)
        else:
            v = c.get(k, MISS)
            if v is not MISS:
                want, exp = truth.get(k, (None, 0.0))
                if clock.now >= exp:
                    raise Fail(f"returned an expired entry (key {k}, {clock.now - exp:.3f}s past its ttl)")
                if v != want:
                    raise Fail(f"returned a stale value for key {k}: {v}, latest set was {want}")
        if n % 97 == 0 and len(c) > cap:
            raise Fail(f"holds {len(c)} entries, capacity is {cap}")
    took = time.monotonic() - t0
    if took > 8:
        raise Fail(f"{ops} operations took {took:.1f}s (is set() or get() scanning every entry?)")
    s = c.stats()
    return f"{ops} ops on a full cache in {took:.1f}s, never over {cap}, nothing expired or stale returned; hit rate {s['hit_rate']:.0%}"


def test_stats() -> str:
    c, clock = make(2, 10)
    s0 = c.stats()
    if s0.get("hit_rate") != 0.0:
        raise Fail(f"hit_rate before any get() should be 0.0, got {s0.get('hit_rate')}")
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")           # hit
    c.get("nope")        # miss
    c.set("c", 3)        # evicts b (a was used more recently)
    clock.advance(11)
    c.get("a")           # miss: expired
    s = c.stats()
    want = {"hits": 1, "misses": 2, "evictions": 1}
    got = {k: s.get(k) for k in want}
    if got != want:
        raise Fail(f"stats {got}, expected {want}")
    if abs(s.get("hit_rate", -1) - 1 / 3) > 1e-9:
        raise Fail(f"hit_rate {s.get('hit_rate')}, expected 1/3")
    return "hits, misses, evictions and hit_rate counted correctly"


def test_threads() -> str:
    from cache import TTLCache

    sys.setswitchinterval(1e-6)  # switch threads constantly to expose races
    c = TTLCache(50, 0.02)
    gets_per_thread = [0] * 8
    errors: list[str] = []

    def worker(w: int) -> None:
        rng = random.Random(w)
        try:
            for _ in range(15_000):
                k = rng.randrange(200)
                if rng.random() < 0.5:
                    c.set(k, w)
                else:
                    c.get(k)
                    gets_per_thread[w] += 1
        except NotImplementedError:
            errors.append("not implemented")
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(w,), daemon=True) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
        if t.is_alive():
            raise Fail("threads still running after 60s (deadlock?)")
    if "not implemented" in errors:
        raise NotImplementedError
    if errors:
        raise Fail(f"a thread crashed: {errors[0]}")
    if len(c) > 50:
        raise Fail(f"holds {len(c)} entries after concurrent use, capacity is 50")
    s = c.stats()
    total = sum(gets_per_thread)
    if s["hits"] + s["misses"] != total:
        raise Fail(f"{total} gets happened but hits + misses = {s['hits'] + s['misses']} (lost updates)")
    return f"8 threads x 15,000 ops: no crash, never over capacity, all {total} gets counted"


TESTS = {
    "basics": (test_basics, 10),
    "expiry": (test_expiry, 10),
    "lru-order": (test_lru, 10),
    "expired-first": (test_expired_first, 10),
    "no-lingering": (test_no_lingering, 15),
    "overload": (test_overload, 25),
    "stats": (test_stats, 10),
    "threads": (test_threads, 90),
}


def run_one(name: str) -> int:
    fn, _ = TESTS[name]
    try:
        print(fn())
        return 0
    except NotImplementedError:
        print("not implemented yet")
    except Fail as e:
        print(e)
    except Exception:
        print("crashed: " + traceback.format_exc(limit=3).strip().splitlines()[-1])
    return 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--one":
        code = run_one(sys.argv[2])
        sys.stdout.flush()
        os._exit(code)
    failed = 0
    for name, (_, deadline) in TESTS.items():
        try:
            r = subprocess.run([sys.executable, __file__, "--one", name],
                               capture_output=True, text=True, timeout=deadline)
            msg = (r.stdout.strip() or r.stderr.strip() or "no output").splitlines()
            ok = r.returncode == 0
            detail = msg[0] if ok else "\n        ".join(msg[:6])
        except subprocess.TimeoutExpired:
            ok, detail = False, f"hung or too slow: over {deadline}s"
        print(f"{'pass' if ok else 'FAIL'}  {name:14} {detail}")
        failed += not ok
    print("LAB PASSED" if not failed else "lab not passed yet")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
