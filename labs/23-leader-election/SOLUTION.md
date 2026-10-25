# Lab 23 · Solution (spoilers)

## The idea in three lines

- **Lease:** you're leader only while you hold an unexpired lease, and you keep
  it alive by renewing it every tick.
- **Safety margin:** stop acting a bit *before* the lease runs out, so a slow tick
  or a little clock drift doesn't leave you acting on a lease that's gone.
- **Fencing token:** every write carries the lease's term. Storage refuses any
  token lower than one it has seen, and the node steps down when that happens.

## Reference `node.py`

```python
"""Reference node: lease + renew + local expiry check + fencing token."""

from cluster import Coordinator, Lease, StaleTokenError, Storage

SAFETY_MARGIN = 0.2  # stop acting this long before the lease runs out


class Node:
    def __init__(self, node_id: str, coordinator: Coordinator, storage: Storage) -> None:
        self.node_id = node_id
        self.coordinator = coordinator
        self.storage = storage
        self.lease: Lease | None = None
        self.writes = 0

    @property
    def is_leader(self) -> bool:
        return self.lease is not None

    def step_down(self) -> None:
        self.lease = None

    def tick(self, now: float) -> None:
        # 1. Don't trust a lease that's about to run out (or already has).
        if self.lease is not None and now >= self.lease.expires_at - self.coordinator.ttl * SAFETY_MARGIN:
            self.step_down()

        # 2. Become leader, or keep the lease alive.
        if self.lease is None:
            self.lease = self.coordinator.try_acquire(self.node_id)
            if self.lease is None:
                return
        else:
            self.lease = self.coordinator.renew(self.node_id, self.lease.term)
            if self.lease is None:
                return

        # 3. Do the leader's job, fenced by the term.
        try:
            self.storage.write(self.node_id, token=self.lease.term, value=f"{self.node_id}:{self.writes}")
            self.writes += 1
        except StaleTokenError:
            self.step_down()
```

## Why the fencing token is the part that matters

The first two rules make a correct node *behave*. They can't make a frozen one
behave. In the pause test the leader checks its lease (valid), starts writing,
and freezes for 3 seconds. A new leader is elected with term N+1 and writes. The
old write then lands carrying term N, and storage refuses it because it has
already seen N+1. Without the token storage can't tell, and the write from a
leader that no longer exists goes through.

This is the core of Martin Kleppmann's argument about distributed locks
("How to do distributed locking", 2016): **a lock or lease gives you no safety
on its own, only the resource that checks a fencing token does.** The token has to
come from the lock service, which is the only place that can hand out an
increasing number. A node-chosen token (a constant, a timestamp, the node's
name) proves nothing. `check.sh`'s "every term's writes came from a single node"
catches that.

## Details worth knowing

- **The renew interval.** Renewing every tick is simple. Real systems renew at
  about a third of the TTL, so one or two lost renew messages don't cost the lease.
- **Clocks.** This lab cheats: everyone shares one `time.monotonic()`. Across
  machines, the node's clock and the coordinator's disagree a little and drift.
  The safety margin absorbs some of that. Fencing makes the rest harmless.
- **Never wall-clock time.** `time.time()` can jump backwards (NTP), and a lease
  measured with it can look valid forever. Durations should come from monotonic clocks.
- **What this lab doesn't cover:** making the coordinator itself fault-tolerant.
  The coordinator here is one process, a single point of failure. etcd and
  ZooKeeper replicate it with a consensus protocol (Raft, Zab) so that a majority
  agreeing on the lease holder survives machine failures. That's a lab of its own
  (Raft is in Track B4). Also not covered: storage that *can't* check tokens, which
  is most external APIs. There you need idempotent writes or a different design.
