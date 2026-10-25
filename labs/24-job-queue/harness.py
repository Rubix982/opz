"""check.sh's test harness: unit checks, then real worker processes under chaos."""

import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from jobqueue import JobQueue

HERE = Path(__file__).resolve().parent
PY = sys.executable
failures = 0


def report(ok: bool, msg: str) -> None:
    global failures
    print(("pass  " if ok else "FAIL  ") + msg, flush=True)
    failures += 0 if ok else 1


def attempt(name: str, fn) -> None:
    try:
        fn()
    except NotImplementedError:
        report(False, f"{name}: not implemented yet")
    except Exception as e:
        report(False, f"{name}: crashed with {type(e).__name__}: {e}")


def check_durable_enqueue(tmp: Path) -> None:
    db = tmp / "durable.db"
    code = ("import sys, time; sys.path.insert(0, %r); from jobqueue import JobQueue\n"
            "q = JobQueue(%r)\n"
            "for i in range(50): q.enqueue(f'job-{i}')\n"
            "print('enqueued', flush=True); time.sleep(60)\n") % (str(HERE), str(db))
    p = subprocess.Popen([PY, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = p.stdout.readline().strip() if p.stdout else ""
    p.send_signal(signal.SIGKILL)
    p.wait()
    if line != "enqueued":
        err = p.stderr.read().strip().splitlines()[-1:] if p.stderr else []
        report(False, f"durability: enqueue process failed ({err[0] if err else 'no output'})")
        return
    q = JobQueue(str(db))
    n = q.counts().get("ready")
    q.close()
    report(n == 50, f"durability: 50 jobs enqueued, process SIGKILLed, {n} still there after reopening")


def check_visibility_and_receipts(tmp: Path) -> None:
    q = JobQueue(str(tmp / "vis.db"), visibility_timeout=0.5)
    jid = q.enqueue("x")
    r1 = q.reserve("a")
    r2 = q.reserve("b")
    ok1 = r1 is not None and r1.job_id == jid and r1.attempt == 1 and r2 is None
    report(ok1, "reserve: a reserved job is hidden from other workers")
    time.sleep(0.65)
    r3 = q.reserve("b")
    ok2 = r3 is not None and r3.job_id == jid and r3.attempt == 2
    report(ok2, "visibility timeout: an un-acked job comes back, as attempt 2")
    if r1 and r3:
        late = q.ack(jid, r1.receipt)
        fresh = q.ack(jid, r3.receipt)
        report(late is False and fresh is True and q.counts().get("done") == 1,
               f"receipts: the timed-out worker's ack is refused ({late}), the current one's works ({fresh})")
        report(q.reserve("c") is None, "ack: a done job is never delivered again")
    q.close()


def check_dead_letter(tmp: Path) -> None:
    q = JobQueue(str(tmp / "dlq.db"), visibility_timeout=0.2, max_attempts=3)
    jid = q.enqueue("poison")
    got = []
    for _ in range(4):
        r = q.reserve("w")
        got.append(r.attempt if r else None)
        time.sleep(0.25)
    dead = q.dead_letters()
    report(got == [1, 2, 3, None] and dead == [(jid, "poison", 3)],
           f"dead letters: delivered 3 times, then parked (deliveries {got}, dead {dead})")
    q.close()


def chaos_run(tmp: Path) -> None:
    db, events = str(tmp / "chaos.db"), str(tmp / "events.log")
    vt, work, n_jobs, n_workers = 1.0, 0.05, 80, 4
    q = JobQueue(db, visibility_timeout=vt, max_attempts=3)
    normal = [q.enqueue(f"job-{i}") for i in range(n_jobs)]
    poison = [q.enqueue("poison") for _ in range(3)]
    q.close()

    rng = random.Random(24)
    workers: dict[str, subprocess.Popen] = {}
    serial = 0

    def spawn() -> None:
        nonlocal serial
        serial += 1
        wid = f"w{serial}"
        workers[wid] = subprocess.Popen([PY, str(HERE / "worker.py"), db, wid, events, str(vt), str(work)],
                                        stderr=subprocess.DEVNULL)

    for _ in range(n_workers):
        spawn()
    start, kills, deadline = time.monotonic(), 0, time.monotonic() + 45
    crashed_all = False
    finished = False
    while time.monotonic() < deadline:
        for wid, p in list(workers.items()):
            if p.poll() is not None:
                del workers[wid]
                spawn()
        elapsed = time.monotonic() - start
        if elapsed < 3 and rng.random() < 0.12:
            victim = rng.choice(list(workers))
            workers[victim].send_signal(signal.SIGKILL)
            kills += 1
        if not crashed_all and elapsed > 1.5:
            for p in workers.values():
                p.send_signal(signal.SIGKILL)
            crashed_all = True
        qq = JobQueue(db, visibility_timeout=vt, max_attempts=3)
        c = qq.counts()
        qq.close()
        if c.get("ready") == 0:
            finished = True
            break
        time.sleep(0.1)
    Path(events + ".stop").touch()
    for p in workers.values():
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()

    q = JobQueue(db, visibility_timeout=vt, max_attempts=3)
    counts, dead = q.counts(), q.dead_letters()
    q.close()
    lines = Path(events).read_text().split("\n") if Path(events).exists() else []

    starts: dict[int, list[float]] = defaultdict(list)
    done: dict[int, int] = defaultdict(int)
    acked: set[int] = set()
    redelivered_after_ack: set[int] = set()
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        jid = int(parts[1])
        if parts[0] == "start":
            if jid in acked:
                redelivered_after_ack.add(jid)
            starts[jid].append(float(parts[4]))
        elif parts[0] == "done":
            done[jid] += 1
        elif parts[0] == "acked" and parts[3] == "True":
            acked.add(jid)
    overlaps = sorted(j for j, ts in starts.items()
                      if any(b - a < 0.9 * vt for a, b in zip(sorted(ts), sorted(ts)[1:])))
    lost = [j for j in normal if done[j] == 0]
    dupes = sum(1 for j in normal if done[j] > 1)

    print(f"      chaos: {n_jobs} jobs + 3 poison, {n_workers} workers, {kills} random SIGKILLs "
          f"plus one kill-everything, {time.monotonic() - start:.1f}s", flush=True)
    report(finished, "chaos: the queue drained" + ("" if finished else f" (still {counts} after 45s)"))
    report(not lost and counts.get("done") == n_jobs,
           f"chaos: no job lost ({n_jobs - len(lost)}/{n_jobs} done, queue says {counts.get('done')})")
    report(sorted(j for j, _, a in dead) == sorted(poison) and all(a == 3 for _, _, a in dead)
           and not any(done[j] for j in poison),
           f"chaos: the 3 poison jobs are dead letters after 3 attempts (dead: {len(dead)})")
    report(not overlaps, "chaos: no job was held by two workers at once"
           + (f" (jobs {overlaps[:5]} reserved twice within the visibility timeout)" if overlaps else ""))
    report(not redelivered_after_ack, "chaos: no job delivered again after a successful ack"
           + (f" (jobs {sorted(redelivered_after_ack)[:5]})" if redelivered_after_ack else ""))
    print(f"      {dupes} jobs ran more than once (expected only when a worker died before acking)", flush=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        attempt("durability", lambda: check_durable_enqueue(tmp))
        attempt("visibility/receipts", lambda: check_visibility_and_receipts(tmp))
        attempt("dead letters", lambda: check_dead_letter(tmp))
        if failures == 0:
            attempt("chaos", lambda: chaos_run(tmp))
        else:
            print("      (skipping the chaos run until the basics pass)", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
