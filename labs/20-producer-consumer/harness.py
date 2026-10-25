"""Test harness for lab 20. Run through ./check.sh.

Each test runs in its own subprocess with a deadline, so a deadlocked
implementation shows up as a FAIL line instead of hanging the harness.
"""

import os
import random
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Switch threads far more often than normal, so races show up in seconds.
sys.setswitchinterval(1e-5)


class Fail(Exception):
    pass


def run_threads(threads: list[threading.Thread], deadline: float) -> None:
    for t in threads:
        t.daemon = True
        t.start()
    end = time.monotonic() + deadline
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
        if t.is_alive():
            raise Fail(f"threads still blocked after {deadline:.0f}s (deadlock or lost wakeup?)")


# ---------------------------------------------------------------- tests


def test_basics() -> str:
    from buffer import BoundedBuffer, Empty, Full

    b = BoundedBuffer(3)
    for i in range(3):
        b.put(i)
    if len(b) != 3:
        raise Fail(f"len after 3 puts is {len(b)}")
    t0 = time.monotonic()
    try:
        b.put(99, timeout=0.2)
        raise Fail("put on a full buffer didn't block or raise Full")
    except Full:
        pass
    if time.monotonic() - t0 < 0.15:
        raise Fail("put(timeout=0.2) on a full buffer gave up too early")
    got = [b.get() for _ in range(3)]
    if got != [0, 1, 2]:
        raise Fail(f"not FIFO: got {got}")
    try:
        b.get(timeout=0.2)
        raise Fail("get on an empty buffer didn't block or raise Empty")
    except Empty:
        pass
    return "FIFO order, capacity, Full/Empty timeouts"


def test_stress() -> str:
    from buffer import BoundedBuffer

    rng = random.Random(20)
    cap = 8
    b = BoundedBuffer(cap)
    producers, consumers, per = 6, 6, 4000
    received: list[list[int]] = [[] for _ in range(consumers)]
    errors: list[str] = []
    over: list[int] = []
    stop = object()
    delays = [rng.random() < 0.002 for _ in range(per)]

    def produce(p: int) -> None:
        try:
            for i in range(per):
                b.put(p * per + i)
                n = len(b)
                if n > cap:
                    over.append(n)
        except Exception as e:
            errors.append(f"put() raised {type(e).__name__}{': ' + str(e) if str(e) else ''}")

    def consume(c: int) -> None:
        try:
            while True:
                item = b.get()
                n = len(b)
                if n > cap or n < 0:
                    over.append(n)
                if item is stop:
                    return
                received[c].append(item)
                if delays[len(received[c]) % per]:
                    time.sleep(0.001)  # a slow consumer now and then
        except Exception as e:
            errors.append(f"get() raised {type(e).__name__}{': ' + str(e) if str(e) else ''} with no timeout (woke up to an empty buffer?)")

    ps = [threading.Thread(target=produce, args=(p,)) for p in range(producers)]
    cs = [threading.Thread(target=consume, args=(c,)) for c in range(consumers)]
    for t in cs:
        t.daemon = True
        t.start()
    run_threads(ps, 40)
    for _ in range(consumers):
        b.put(stop)
    end = time.monotonic() + 20
    for t in cs:
        t.join(max(0.0, end - time.monotonic()))
        if t.is_alive():
            raise Fail("consumers still blocked after the producers finished")
    if errors:
        raise Fail(errors[0])
    if over:
        raise Fail(f"buffer held {max(over)} items, capacity is {cap}")
    flat = [x for r in received for x in r]
    expected = producers * per
    if len(flat) != len(set(flat)):
        raise Fail(f"{len(flat) - len(set(flat))} items delivered twice")
    if len(set(flat)) != expected:
        raise Fail(f"{expected - len(set(flat))} of {expected} items lost")
    for r in received:  # each consumer sees each producer's items in order
        last: dict[int, int] = {}
        for x in r:
            p = x // per
            if x < last.get(p, -1):
                raise Fail("items from one producer came out of order")
            last[p] = x
    return f"{producers} producers x {per} items, {consumers} consumers, capacity {cap}: none lost, none doubled, never over capacity"


def test_close() -> str:
    from buffer import BoundedBuffer, Closed

    b = BoundedBuffer(2)
    b.put("a")
    b.put("b")
    outcome: dict[str, object] = {}

    def blocked_put() -> None:
        try:
            b.put("c")
            outcome["put"] = "returned"
        except Closed:
            outcome["put"] = "Closed"

    t = threading.Thread(target=blocked_put, daemon=True)
    t.start()
    time.sleep(0.3)
    b.close()
    t.join(2)
    if t.is_alive():
        raise Fail("a put() blocked on a full buffer didn't wake up on close()")
    if outcome.get("put") != "Closed":
        raise Fail(f"blocked put() after close: {outcome.get('put')} (should raise Closed)")
    try:
        b.put("d")
        raise Fail("put() after close() succeeded")
    except Closed:
        pass
    got = [b.get(), b.get()]
    if got != ["a", "b"]:
        raise Fail(f"close() lost the items still held: {got}")
    try:
        b.get(timeout=1)
        raise Fail("get() on a closed, empty buffer returned something")
    except Closed:
        pass

    # A consumer blocked on an empty buffer must wake when it's closed.
    e = BoundedBuffer(1)
    woke: dict[str, object] = {}

    def blocked_get() -> None:
        try:
            woke["v"] = e.get()
        except Closed:
            woke["v"] = "Closed"

    t = threading.Thread(target=blocked_get, daemon=True)
    t.start()
    time.sleep(0.3)
    e.close()
    t.join(2)
    if t.is_alive():
        raise Fail("a get() blocked on an empty buffer didn't wake up on close()")
    if woke.get("v") != "Closed":
        raise Fail(f"blocked get() after close returned {woke.get('v')!r} (should raise Closed)")
    return "close() wakes blocked threads, refuses new puts, lets gets drain"


def test_no_busy_wait() -> str:
    from buffer import BoundedBuffer, Empty

    b = BoundedBuffer(1)
    cpu0 = time.process_time()
    try:
        b.get(timeout=1.5)
    except Empty:
        pass
    used = time.process_time() - cpu0
    if used > 0.3:
        raise Fail(f"a blocked get() used {used:.2f}s of CPU in 1.5s (polling instead of waiting?)")
    return f"blocked get() used {used * 1000:.0f} ms of CPU in 1.5 s"


def test_transfer() -> str:
    from buffer import Account, transfer

    a, b = Account(1_000_000), Account(1_000_000)
    rounds = 20_000

    errors: list[BaseException] = []

    def mover(src: Account, dst: Account) -> None:
        try:
            for _ in range(rounds):
                transfer(src, dst, 1)
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=mover, args=pair) for pair in ((a, b), (b, a), (a, b), (b, a))]
    run_threads(threads, 30)
    if errors:
        raise errors[0]
    if a.balance + b.balance != 2_000_000:
        raise Fail(f"money created or destroyed: total is {a.balance + b.balance}")
    if a.lock.locked() or b.lock.locked():
        raise Fail("a lock was left held after all transfers finished")
    return f"{4 * rounds} transfers both ways at once, no deadlock, total conserved"


TESTS = {
    "basics": (test_basics, 10),
    "stress": (test_stress, 75),
    "close": (test_close, 15),
    "no-busy-wait": (test_no_busy_wait, 10),
    "transfer-deadlock": (test_transfer, 40),
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
        sys.stdout.flush()
        code = run_one(sys.argv[2])
        sys.stdout.flush()
        os._exit(code)  # don't wait for stuck daemon threads
    failed = 0
    for name, (_, deadline) in TESTS.items():
        try:
            r = subprocess.run([sys.executable, __file__, "--one", name],
                               capture_output=True, text=True, timeout=deadline)
            msg = (r.stdout.strip() or r.stderr.strip() or "no output").splitlines()
            ok = r.returncode == 0
            detail = msg[0] if ok else "\n        ".join(msg[:6])
        except subprocess.TimeoutExpired:
            ok, detail = False, f"hung for {deadline}s (deadlock?)"
        print(f"{'pass' if ok else 'FAIL'}  {name:18} {detail}")
        failed += not ok
    print("LAB PASSED" if not failed else "lab not passed yet")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
