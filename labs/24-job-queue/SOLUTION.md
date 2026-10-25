# Lab 24 · Solution (spoilers)

## The design

One table. Each job row holds its whole state:

| column | meaning |
|---|---|
| `state` | `ready` (waiting or in flight), `done`, `dead` |
| `attempts` | how many times it has been handed out |
| `visible_at` | hidden until this time, so it's in flight when `visible_at` is in the future |
| `receipt` | random token of the current reservation |

- **reserve** = in one transaction: park jobs that are visible again but out of
  attempts, pick the oldest visible job, bump `attempts`, push `visible_at` forward,
  set a new `receipt`.
- **ack** = `UPDATE … SET state='done' WHERE id=? AND receipt=?`. A stale receipt
  matches nothing.
- **crash recovery** = nothing to do. A crashed worker's job simply becomes
  visible when its timeout passes.

## Reference `jobqueue.py`

```python
"""Reference job queue: one SQLite table, every state change in one transaction."""

import sqlite3
import time
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Reserved:
    job_id: int
    payload: str
    attempt: int
    receipt: str


class JobQueue:
    def __init__(self, path: str, visibility_timeout: float = 1.0, max_attempts: int = 3) -> None:
        self.vt = visibility_timeout
        self.max_attempts = max_attempts
        # isolation_level=None: no hidden transactions; we open them ourselves.
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")    # readers don't block the writer
        self.db.execute("PRAGMA synchronous=FULL")    # commit = on disk
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id         INTEGER PRIMARY KEY,
            payload    TEXT NOT NULL,
            state      TEXT NOT NULL DEFAULT 'ready',   -- ready | done | dead
            attempts   INTEGER NOT NULL DEFAULT 0,
            visible_at REAL NOT NULL DEFAULT 0,
            receipt    TEXT)""")

    def enqueue(self, payload: str) -> int:
        cur = self.db.execute("INSERT INTO jobs (payload) VALUES (?)", (payload,))
        return int(cur.lastrowid)  # autocommit: on disk before we return

    def reserve(self, worker_id: str) -> Reserved | None:
        now = time.time()
        # BEGIN IMMEDIATE takes the write lock *before* we look, so two workers
        # can't both see the same job as free.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("""UPDATE jobs SET state = 'dead'
                               WHERE state = 'ready' AND visible_at <= ? AND attempts >= ?""",
                            (now, self.max_attempts))
            row = self.db.execute("""SELECT id, payload, attempts FROM jobs
                                     WHERE state = 'ready' AND visible_at <= ?
                                     ORDER BY id LIMIT 1""", (now,)).fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            receipt = uuid.uuid4().hex
            self.db.execute("UPDATE jobs SET attempts = attempts + 1, visible_at = ?, receipt = ? WHERE id = ?",
                            (now + self.vt, receipt, row[0]))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return Reserved(row[0], row[1], row[2] + 1, receipt)

    def ack(self, job_id: int, receipt: str) -> bool:
        cur = self.db.execute("UPDATE jobs SET state = 'done' WHERE id = ? AND receipt = ? AND state = 'ready'",
                              (job_id, receipt))
        return cur.rowcount == 1

    def dead_letters(self) -> list[tuple[int, str, int]]:
        now = time.time()
        self.db.execute("""UPDATE jobs SET state = 'dead'
                           WHERE state = 'ready' AND visible_at <= ? AND attempts >= ?""",
                        (now, self.max_attempts))
        return [tuple(r) for r in self.db.execute(
            "SELECT id, payload, attempts FROM jobs WHERE state = 'dead' ORDER BY id")]

    def counts(self) -> dict[str, int]:
        self.dead_letters()  # park anything that has run out of attempts
        got = dict(self.db.execute("SELECT state, COUNT(*) FROM jobs GROUP BY state").fetchall())
        return {k: got.get(k, 0) for k in ("ready", "done", "dead")}

    def close(self) -> None:
        self.db.close()
```

## The race that check.sh hunts for

The natural first version reads ("which job is free?") and then writes ("it's
mine"), as two separate statements. Two workers can both read job 42 as free in
between and both claim it. Both run it, and both acks succeed because each wrote
its own receipt last. `BEGIN IMMEDIATE` takes SQLite's write lock *before* the read,
so the second worker waits and then sees job 42 as taken. In Postgres the same
idea is `SELECT … FOR UPDATE SKIP LOCKED`.

## Details worth knowing

- **At-least-once means duplicates will happen.** A worker that finishes the work
  and dies just before `ack` gets the job run again. You can't fix that in the queue.
  You fix it by making the work idempotent: "charge order 7" checks whether order
  7 is already charged, or uses an idempotency key (lab 06's event-ID store, again).
- **"Exactly once" is at-least-once plus idempotency.** Systems that advertise it
  (Kafka transactions, SQS FIFO deduplication) do this inside a boundary they control.
- **Visibility timeout vs. job length.** Too short and slow jobs get redelivered
  while still running, which means duplicates on every slow job. Too long and a crashed
  job waits that long to retry. Real queues let a worker extend its lease (SQS
  `ChangeMessageVisibility`), the same heartbeat idea as lab 23.
- **Dead letters need an owner.** Parking poison jobs keeps the queue healthy, but
  a dead-letter queue nobody watches is a slow-motion data loss. Alert on its size.
- **What this doesn't cover:** many machines. SQLite on one disk is the whole
  system here. Spreading a queue across machines brings back every lab-23 problem:
  who owns a partition, and what a paused node does when it wakes up.
