"""The cluster around your nodes. Don't edit this file; build node.py.

Three pieces, all in one process so the lab is easy to run and watch:

- Coordinator: a tiny lease service, like a lock in etcd/ZooKeeper/Consul.
  One node at a time can hold the lease. A lease lasts TTL seconds unless renewed.
  Every new grant gets a higher term number.
- Storage: the shared resource only the leader should write to. It checks fencing
  tokens: a write whose token is lower than one it has already seen is refused.
- NodeRunner: runs one node in its own thread, calling node.tick(now) every
  TICK seconds. The harness can kill a runner (it stops for good) or pause a
  node in the middle of a write, the way a long GC pause or a frozen VM would.

`now` everywhere is time.monotonic(), the same clock the coordinator uses.
"""

import threading
import time
from dataclasses import dataclass

TTL = 1.0      # seconds a lease lasts without renewal
TICK = 0.05    # seconds between node.tick() calls


@dataclass(frozen=True)
class Lease:
    term: int          # increases with every new grant; use it as the fencing token
    expires_at: float  # coordinator clock (time.monotonic())


class StaleTokenError(Exception):
    """Storage refused a write: a higher fencing token has been seen."""


class Coordinator:
    def __init__(self, ttl: float = TTL) -> None:
        self.ttl = ttl
        self._lock = threading.Lock()
        self._holder: str | None = None
        self._term = 0
        self._expires = 0.0

    def try_acquire(self, node_id: str) -> Lease | None:
        """Get the lease if nobody holds a live one. Returns None otherwise."""
        with self._lock:
            now = time.monotonic()
            if self._holder is not None and now < self._expires:
                return None
            self._term += 1
            self._holder, self._expires = node_id, now + self.ttl
            return Lease(self._term, self._expires)

    def renew(self, node_id: str, term: int) -> Lease | None:
        """Extend a live lease you hold. None if it expired or someone else has it."""
        with self._lock:
            now = time.monotonic()
            if self._holder != node_id or self._term != term or now >= self._expires:
                return None
            self._expires = now + self.ttl
            return Lease(self._term, self._expires)


@dataclass
class WriteRecord:
    at: float
    node_id: str
    token: int
    value: str
    accepted: bool


class Storage:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.highest_token = 0
        self.log: list[WriteRecord] = []
        self._pause_next: dict[str, float] = {}

    def pause_next_write(self, node_id: str, seconds: float) -> None:
        """Harness only: the node's next write stalls this long before it lands."""
        self._pause_next[node_id] = seconds

    def write(self, node_id: str, token: int, value: str) -> None:
        """Write as node_id with a fencing token. Raises StaleTokenError if refused."""
        if (pause := self._pause_next.pop(node_id, None)) is not None:
            time.sleep(pause)  # the "GC pause": the node checked its lease, then froze
        with self._lock:
            ok = token >= self.highest_token
            if ok:
                self.highest_token = token
            self.log.append(WriteRecord(time.monotonic(), node_id, token, value, ok))
        if not ok:
            raise StaleTokenError(f"token {token} < {self.highest_token}")


class NodeRunner:
    def __init__(self, node: object) -> None:
        self.node = node
        self.errors: list[str] = []
        self._killed = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def kill(self) -> None:
        self._killed.set()

    @property
    def alive(self) -> bool:
        return not self._killed.is_set()

    def _run(self) -> None:
        while not self._killed.is_set():
            try:
                self.node.tick(time.monotonic())  # type: ignore[attr-defined]
            except Exception as e:  # keep running; the harness reports these
                if len(self.errors) < 5:
                    self.errors.append(f"{type(e).__name__}: {e}")
            time.sleep(TICK)
