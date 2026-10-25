"""Test harness for lab 39. Run through ./check.sh.

Builds a 5-node cluster of your Node class on the fake network in net.py, then
partitions it in different shapes while clients read and write, and checks what
was acknowledged against what survives. Each test runs in its own process with a
deadline, so an operation that hangs is a FAIL, not a frozen terminal.
"""

import bisect
import os
import random
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

N = 5
OP_LIMIT = 2.0  # seconds any single put/get may take


class Fail(Exception):
    pass


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise Fail(msg)


def cluster(seed: int = 0):
    from net import Network
    from node import Node

    net = Network(seed)
    nodes = [Node(i, list(range(N)), net) for i in range(N)]
    return net, nodes


def refused(fn, *args) -> bool:
    """True if the call raised NoQuorum; False if it returned."""
    from node import NoQuorum

    try:
        fn(*args)
        return False
    except NoQuorum:
        return True


@dataclass
class Op:
    kind: str          # "put" or "get"
    node: int
    key: str
    value: object
    version: tuple | None
    start: float
    end: float
    ok: bool


class Recorder:
    """Runs operations, times them, and keeps the history."""

    def __init__(self):
        self.ops: list[Op] = []
        self.lock = threading.Lock()
        self.errors: list[str] = []
        self.unimplemented = False

    def check(self) -> None:
        if self.unimplemented:
            raise NotImplementedError
        expect(not self.errors, self.errors[0] if self.errors else "")

    def run(self, kind: str, node, key: str, value=None) -> Op:
        from node import NoQuorum

        t0 = time.monotonic()
        ok, version, got = False, None, value
        try:
            if kind == "put":
                version = tuple(node.put(key, value))
            else:
                got, version = node.get(key)
                version = tuple(version)
            ok = True
        except NoQuorum:
            pass
        except NotImplementedError:
            self.unimplemented = True
            raise
        except Exception as e:
            with self.lock:
                self.errors.append(f"{kind} via node {node.id}: {type(e).__name__}: {e}")
        t1 = time.monotonic()
        if t1 - t0 > OP_LIMIT:
            with self.lock:
                self.errors.append(f"{kind} via node {node.id} took {t1 - t0:.1f}s")
        op = Op(kind, node.id, key, got, version, t0, t1, ok)
        with self.lock:
            self.ops.append(op)
        return op


def check_final(nodes, rec: Recorder, keys) -> None:
    """After healing: every node returns, per key, nothing older than the newest acknowledged write."""
    for key in keys:
        acked = [o for o in rec.ops if o.kind == "put" and o.ok and o.key == key]
        attempted = {o.value for o in rec.ops if o.kind == "put" and o.key == key}
        if not acked:
            continue
        newest = max(acked, key=lambda o: o.version)
        for n in nodes:
            value, version = n.get(key)
            version = tuple(version)
            expect(version >= newest.version,
                   f"key {key!r} via node {n.id}: version {version} is older than the acknowledged "
                   f"write {newest.value!r} at {newest.version}: an acknowledged write was lost")
            if version == newest.version:
                expect(value == newest.value,
                       f"key {key!r}: version {version} holds {value!r}, but the write acknowledged "
                       f"with that version was {newest.value!r}")
            else:
                expect(value in attempted, f"key {key!r} holds {value!r}, which nobody wrote")


def read_violations(rec: Recorder, key: str) -> list[str]:
    """Reads must never go back in time, for one client or across clients.

    A read that starts after an acknowledged write ended must see it (or newer),
    and a read that starts after another read ended must not return less.
    """
    reads = [o for o in rec.ops if o.kind == "get" and o.ok and o.key == key]
    writes = [o for o in rec.ops if o.kind == "put" and o.ok and o.key == key]
    bad: list[str] = []
    for label, done in (("an acknowledged write", writes), ("another read", reads)):
        done = sorted(done, key=lambda o: o.end)
        ends = [o.end for o in done]
        best: list[tuple] = []  # best[i] = newest version among done[:i+1]
        for o in done:
            best.append(o.version if not best or o.version > best[-1] else best[-1])
        for r in reads:
            i = bisect.bisect_left(ends, r.start) - 1
            if i >= 0 and r.version < best[i]:
                bad.append(f"read via node {r.node} returned {r.version} after {label} had "
                           f"already seen {best[i]}: time went backwards")
    return bad


# ---------------------------------------------------------------- tests


def test_basics() -> str:
    from node import MISSING

    _, nodes = cluster()
    v1 = nodes[0].put("k", "one")
    value, version = nodes[3].get("k")
    expect(value == "one", f"put 'one' via node 0, get via node 3 -> {value!r}")
    expect(tuple(version) == tuple(v1), f"get returned version {version}, put returned {v1}")
    v2 = nodes[4].put("k", "two")
    expect(tuple(v2) > tuple(v1), f"second put got version {v2}, not newer than {v1}")
    expect(nodes[1].get("k")[0] == "two", "overwrite via another node not visible")
    value, version = nodes[2].get("never-written")
    expect(value is None and tuple(version) == tuple(MISSING), f"missing key -> {(value, version)}")
    return "put/get through different nodes, versions increase, missing keys"


def test_minority() -> str:
    net, nodes = cluster()
    nodes[2].put("k", "before")
    net.partition({0, 1}, {2, 3, 4})
    for i in (0, 1):
        expect(refused(nodes[i].put, "k", f"minority-{i}"), f"node {i} (minority side, 2 of 5) accepted a write")
        expect(refused(nodes[i].get, "k"), f"node {i} (minority side) answered a read it can't vouch for")
    nodes[3].put("k", "majority")
    expect(nodes[4].get("k")[0] == "majority", "majority side can't read its own write")
    net.partition({4}, {0, 1, 2, 3})
    expect(refused(nodes[4].put, "k", "alone"), "a node cut off on its own accepted a write")
    net.heal()
    for n in nodes:
        value = n.get("k")[0]
        expect(value == "majority", f"after healing, node {n.id} reads {value!r}: a refused write surfaced")
    return "2-node and 1-node minorities refuse reads and writes; the majority keeps going; nothing refused surfaces"


def test_no_majority() -> str:
    net, nodes = cluster()
    nodes[0].put("k", "v")
    net.partition({0, 1}, {2, 3}, {4})
    for n in nodes:
        expect(refused(n.put, "k", "x"), f"node {n.id} accepted a write with no majority anywhere")
        expect(refused(n.get, "k"), f"node {n.id} answered a read with no majority anywhere")
    net.heal()
    nodes[4].put("k", "after")
    expect(nodes[0].get("k")[0] == "after", "cluster didn't recover after a 2-2-1 split healed")
    return "a 2-2-1 split refuses everything, then recovers"


def test_stale_coordinator() -> str:
    net, nodes = cluster()
    net.partition({4}, {0, 1, 2, 3})
    last = None
    for i in range(1, 6):
        last = nodes[0].put("k", i)
    net.heal()
    v = nodes[4].put("k", "x")  # node 4 missed all five writes
    expect(tuple(v) > tuple(last),
           f"node 4 wrote with version {v}, older than {last} which a majority already has: "
           "its write will lose to old data")
    for n in nodes:
        value = n.get("k")[0]
        expect(value == "x", f"node {n.id} reads {value!r} after node 4 wrote 'x'")
    return "a node that was cut off picks a version newer than the majority's, and its write wins"


SHAPES = [
    ({0, 1}, {2, 3, 4}),
    ({4}, {0, 1, 2, 3}),
    ({0, 1, 2}, {3, 4}),
    ({2}, {0, 1, 3, 4}),
    ({0, 4}, {1, 2, 3}),
]


def test_shapes() -> str:
    net, nodes = cluster(seed=39)
    rec = Recorder()
    keys = ["a", "b", "c"]
    seq = [0]
    for shape in SHAPES:
        net.partition(*shape)
        minority = min(shape, key=len)
        stop = threading.Event()

        def writer(n) -> None:
            rng = random.Random(n.id)
            while not stop.is_set():
                seq[0] += 1
                rec.run("put", n, rng.choice(keys), f"n{n.id}-{seq[0]}")
                time.sleep(0.005)

        def reader(n) -> None:
            rng = random.Random(100 + n.id)
            while not stop.is_set():
                rec.run("get", n, rng.choice(keys))
                time.sleep(0.005)

        t_start = time.monotonic()
        threads = [threading.Thread(target=f, args=(n,), daemon=True) for n in nodes for f in (writer, reader)]
        for t in threads:
            t.start()
        time.sleep(0.4)
        stop.set()
        for t in threads:
            t.join(OP_LIMIT + 1)
        expect(not any(t.is_alive() for t in threads), f"operations hung during partition {shape}")
        rec.check()
        phase = [o for o in rec.ops if o.start >= t_start and o.kind == "put"]
        for n in nodes:
            acked = sum(o.ok for o in phase if o.node == n.id)
            if n.id in minority:
                expect(acked == 0, f"partition {shape}: node {n.id} on the minority side acknowledged {acked} writes")
            else:
                expect(acked > 0, f"partition {shape}: node {n.id} on the majority side acknowledged no writes")
    rec.check()
    net.heal()
    check_final(nodes, rec, keys)
    for key in keys:
        bad = read_violations(rec, key)
        expect(not bad, f"{len(bad)} reads went back in time, first: {bad[0] if bad else ''}")
    acked = sum(o.ok for o in rec.ops if o.kind == "put")
    return (f"{len(SHAPES)} partition shapes, {acked} acknowledged writes: minorities refused, "
            "majorities kept going, nothing lost after healing")


def test_reads() -> str:
    net, nodes = cluster(seed=7)
    net.drop_rate = 0.05  # some writes land on only part of a quorum
    rec = Recorder()
    stop = threading.Event()
    rng_shape = random.Random(3)

    def shaper() -> None:
        while not stop.is_set():
            net.partition(*rng_shape.choice(SHAPES))
            time.sleep(0.12)
        net.heal()

    def writer() -> None:
        rng = random.Random(1)
        i = 0
        while not stop.is_set():
            i += 1
            rec.run("put", nodes[rng.randrange(N)], "n", i)

    def reader(r: int) -> None:
        rng = random.Random(50 + r)
        while not stop.is_set():
            rec.run("get", nodes[rng.randrange(N)], "n")

    threads = [threading.Thread(target=shaper, daemon=True), threading.Thread(target=writer, daemon=True)]
    threads += [threading.Thread(target=reader, args=(r,), daemon=True) for r in range(4)]
    for t in threads:
        t.start()
    time.sleep(4)
    stop.set()
    for t in threads:
        t.join(OP_LIMIT + 1)
    expect(not any(t.is_alive() for t in threads), "operations hung")
    rec.check()
    reads = sum(o.ok for o in rec.ops if o.kind == "get")
    expect(reads > 50, f"only {reads} reads succeeded in 4s; the majority side should keep answering")
    bad = read_violations(rec, "n")
    expect(not bad, f"{len(bad)} reads went back in time, first: {bad[0] if bad else ''}")
    return f"{reads} reads during shifting partitions and lost messages; none went back in time"


def test_flapping() -> str:
    net, nodes = cluster(seed=11)
    net.drop_rate = 0.15
    net.delay = (0.0, 0.002)
    rec = Recorder()
    stop = threading.Event()
    keys = ["x", "y", "z"]

    def flapper() -> None:
        rng = random.Random(5)
        while not stop.is_set():
            ids = list(range(N))
            rng.shuffle(ids)
            cut = rng.randint(1, N - 1)
            net.partition(set(ids[:cut]), set(ids[cut:]))
            time.sleep(rng.uniform(0.005, 0.03))
            if rng.random() < 0.3:
                net.heal()
                time.sleep(rng.uniform(0.005, 0.03))

    def client(c: int) -> None:
        rng = random.Random(200 + c)
        for i in range(80):
            n = nodes[rng.randrange(N)]
            if rng.random() < 0.5:
                rec.run("put", n, rng.choice(keys), f"c{c}-{i}")
            else:
                rec.run("get", n, rng.choice(keys))

    flap = threading.Thread(target=flapper, daemon=True)
    flap.start()
    clients = [threading.Thread(target=client, args=(c,), daemon=True) for c in range(5)]
    for t in clients:
        t.start()
    for t in clients:
        t.join(25)
    stop.set()
    flap.join(2)
    expect(not any(t.is_alive() for t in clients), "operations hung while links flapped")
    rec.check()
    net.heal()
    net.drop_rate = 0.0
    check_final(nodes, rec, keys)
    for key in keys:
        bad = read_violations(rec, key)
        expect(not bad, f"{len(bad)} reads went back in time, first: {bad[0] if bad else ''}")
    for n in nodes:  # recovered: every node can coordinate again
        n.put("after", n.id)
    expect(nodes[0].get("after")[0] == N - 1, "cluster didn't recover after the links stopped flapping")
    ok = sum(o.ok for o in rec.ops)
    return f"400 operations while links flapped and 15% of messages were lost ({ok} succeeded); consistent after healing"


TESTS = {
    "basics": (test_basics, 10),
    "minority-refuses": (test_minority, 10),
    "no-majority": (test_no_majority, 10),
    "stale-coordinator": (test_stale_coordinator, 10),
    "partition-shapes": (test_shapes, 30),
    "reads-go-forward": (test_reads, 30),
    "flapping-links": (test_flapping, 40),
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
        os._exit(code)
    only = sys.argv[1:]
    failed = 0
    for name, (_, deadline) in TESTS.items():
        if only and name not in only:
            continue
        try:
            r = subprocess.run([sys.executable, __file__, "--one", name],
                               capture_output=True, text=True, timeout=deadline)
            msg = (r.stdout.strip() or r.stderr.strip() or "no output").splitlines()
            ok = r.returncode == 0
            detail = msg[0] if ok else "\n        ".join(msg[:6])
        except subprocess.TimeoutExpired:
            ok, detail = False, f"hung for {deadline}s"
        print(f"{'pass' if ok else 'FAIL'}  {name:18} {detail}")
        failed += not ok
    print("LAB PASSED" if not failed else "lab not passed yet")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
