"""Test harness for lab 21. Run through ./check.sh.

The breaker gets a fake clock the harness moves by hand, so "30 seconds later"
takes no time. Each test runs in its own subprocess with a deadline.
"""

import os
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.setswitchinterval(1e-5)


class Fail(Exception):
    pass


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Dependency:
    """A downstream service the harness can make healthy, failing, or slow."""

    def __init__(self) -> None:
        self.mode = "healthy"
        self.calls = 0
        self.lock = threading.Lock()
        self.gate: threading.Event | None = None

    def __call__(self, x: int = 0) -> str:
        with self.lock:
            self.calls += 1
        if self.gate is not None:
            self.gate.wait(10)
        if self.mode == "failing":
            raise ConnectionError("downstream refused")
        if self.mode == "slow":
            time.sleep(0.1)  # waits out the client's timeout...
            raise TimeoutError("downstream timed out")
        return f"ok {x}"


def fb() -> str:
    return "fallback"


def make(threshold: int = 5, timeout: float = 30.0):
    from breaker import CircuitBreaker

    clock = FakeClock()
    return CircuitBreaker(failure_threshold=threshold, reset_timeout=timeout, clock=clock), clock, Dependency()


def expect_state(b, want: str, when: str) -> None:
    got = b.state
    if got != want:
        raise Fail(f"{when}: state is {got!r}, should be {want!r}")


# ---------------------------------------------------------------- tests


def test_closed() -> str:
    b, _, dep = make()
    expect_state(b, "closed", "new breaker")
    if b.call(dep, 7) != "ok 7":
        raise Fail("a healthy call didn't return the dependency's result")
    dep.mode = "failing"
    try:
        b.call(dep)
        raise Fail("a failing call without a fallback didn't raise")
    except ConnectionError:
        pass
    except Exception as e:
        raise Fail(f"a failing call raised {type(e).__name__}, should re-raise the original ConnectionError")
    if b.call(dep, fallback=fb) != "fallback":
        raise Fail("a failing call with a fallback didn't return fallback()")
    for _ in range(2):
        b.call(dep, fallback=fb)
    expect_state(b, "closed", "after 4 failures with threshold 5")
    dep.mode = "healthy"
    b.call(dep)
    dep.mode = "failing"
    for _ in range(4):
        b.call(dep, fallback=fb)
    expect_state(b, "closed", "after 4 failures, 1 success, 4 failures (count must be consecutive)")
    return "passes calls through, re-raises or falls back, counts only consecutive failures"


def test_opens() -> str:
    b, clock, dep = make()
    dep.mode = "failing"
    for _ in range(5):
        b.call(dep, fallback=fb)
    expect_state(b, "open", "after 5 consecutive failures")
    before = dep.calls
    dep.mode = "healthy"  # even if it recovered, we don't know yet
    for _ in range(100):
        if b.call(dep, fallback=fb) != "fallback":
            raise Fail("an open breaker didn't return the fallback")
    try:
        b.call(dep)
        raise Fail("an open breaker with no fallback didn't raise CircuitOpen")
    except Exception as e:
        if type(e).__name__ != "CircuitOpen":
            raise Fail(f"an open breaker raised {type(e).__name__}, should raise CircuitOpen")
    clock.advance(29.9)
    b.call(dep, fallback=fb)
    if dep.calls != before:
        raise Fail(f"the dependency was called {dep.calls - before} times while the breaker was open")
    return "opens at the threshold, refuses calls without touching the dependency until the timeout"


def test_half_open() -> str:
    b, clock, dep = make()
    dep.mode = "failing"
    for _ in range(5):
        b.call(dep, fallback=fb)
    clock.advance(30)
    n = dep.calls
    b.call(dep, fallback=fb)  # trial: still failing
    if dep.calls != n + 1:
        raise Fail(f"after the timeout, {dep.calls - n} calls reached the dependency (should be exactly one trial)")
    expect_state(b, "open", "after a failed trial")
    clock.advance(29)
    b.call(dep, fallback=fb)
    if dep.calls != n + 1:
        raise Fail("after a failed trial the timeout didn't start over (a call got through 29s later)")
    clock.advance(1)
    dep.mode = "healthy"
    if b.call(dep, 3) != "ok 3":
        raise Fail("a successful trial didn't return the real result")
    expect_state(b, "closed", "after a successful trial")
    dep.mode = "failing"
    for _ in range(4):
        b.call(dep, fallback=fb)
    expect_state(b, "closed", "4 failures after recovering (the count should have reset)")
    return "one trial after the timeout; a failed trial restarts the timer; a good one closes"


def test_herd() -> str:
    b, clock, dep = make()
    dep.mode = "failing"
    for _ in range(5):
        b.call(dep, fallback=fb)
    clock.advance(30)
    dep.mode = "healthy"
    dep.gate = threading.Event()  # the trial call will hang until we release it
    n = dep.calls
    results: list[str] = []
    errors: list[str] = []
    rlock = threading.Lock()

    def caller() -> None:
        try:
            r = b.call(dep, fallback=fb)
            with rlock:
                results.append(r)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=caller, daemon=True) for _ in range(50)]
    for t in threads:
        t.start()
    time.sleep(1.0)
    reached = dep.calls - n
    fast = len(results)
    dep.gate.set()
    for t in threads:
        t.join(5)
    if errors:
        raise Fail(errors[0])
    if reached != 1:
        raise Fail(f"{reached} of 50 simultaneous callers reached the recovering dependency (should be 1: the trial)")
    if fast < 49:
        raise Fail(f"only {fast} of the 49 non-trial callers got an answer while the trial ran (the rest waited on it)")
    expect_state(b, "closed", "after the trial succeeded")
    return "50 callers at once after the timeout: 1 trial, 49 instant fallbacks"


def test_slow_dependency() -> str:
    b, clock, dep = make()
    for _ in range(20):
        b.call(dep, fallback=fb)
    dep.mode = "slow"
    t0 = time.monotonic()
    for _ in range(200):
        b.call(dep, fallback=fb)
    took = time.monotonic() - t0
    if took > 2.0:
        raise Fail(f"200 calls to a slow dependency took {took:.1f}s (each one waited for the timeout)")
    dep.mode = "healthy"
    clock.advance(31)
    good = [b.call(dep, i, fallback=fb) for i in range(20)]
    if good != [f"ok {i}" for i in range(20)]:
        raise Fail("after the dependency recovered and the timeout passed, calls didn't go through again")
    return f"200 calls while slow took {took:.2f}s (not 20s); closes on its own after recovery"


TESTS = {
    "closed": (test_closed, 10),
    "opens": (test_opens, 10),
    "half-open": (test_half_open, 10),
    "thundering-herd": (test_herd, 20),
    "slow-dependency": (test_slow_dependency, 30),
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
            ok, detail = False, f"hung for {deadline}s"
        print(f"{'pass' if ok else 'FAIL'}  {name:16} {detail}")
        failed += not ok
    print("LAB PASSED" if not failed else "lab not passed yet")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
