"""Your node. Build this.

A node is ticked every 50 ms by its runner (see cluster.py). On each tick it
should either try to become leader, or, if it is the leader, keep its lease alive
and do the leader's job: write to storage.

The contract (check.sh tests all of it):
- At most one node acts as leader at a time. A node that can't prove it still
  holds the lease must stop acting as leader.
- When the leader dies, another node takes over within about TTL + 1 second.
- Every write carries a fencing token, so storage can refuse a write from a
  leader that has been replaced but doesn't know it yet.
- A node whose write is refused steps down immediately.
"""

from cluster import Coordinator, Lease, StaleTokenError, Storage  # noqa: F401


class Node:
    def __init__(self, node_id: str, coordinator: Coordinator, storage: Storage) -> None:
        self.node_id = node_id
        self.coordinator = coordinator
        self.storage = storage
        self.lease: Lease | None = None
        self.writes = 0

    @property
    def is_leader(self) -> bool:
        """True while this node believes it is the leader."""
        raise NotImplementedError

    def tick(self, now: float) -> None:
        """One step. `now` is time.monotonic(), the coordinator's clock.

        As leader, write one value per tick:
            self.storage.write(self.node_id, token=..., value=f"{self.node_id}:{self.writes}")
        """
        raise NotImplementedError
