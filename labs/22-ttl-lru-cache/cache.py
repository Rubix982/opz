"""Lab 22: an in-memory cache with expiry (TTL) and a size cap (LRU eviction).

Build everything marked `raise NotImplementedError`. Standard library only.
The harness (`./check.sh`) imports this file, gives it a fake clock, and
overloads it.
"""

import threading
import time
from typing import Any, Callable, Hashable


class TTLCache:
    """A thread-safe cache holding at most `capacity` entries.

    Expiry:
    - set(key, value, ttl) at time t makes the entry expire at t + ttl
      (`ttl` defaults to the cache's ttl). From that moment on (clock() >= t + ttl)
      get() must never return it.
    - Expired entries must not pile up in memory: after any set(), the cache
      holds no expired entries. len(cache) counts what is held in memory, live or not.

    Eviction:
    - The cache never holds more than `capacity` entries.
    - When a new key arrives and the cache is full, expired entries go first.
      Only if it's still full is a live entry evicted: the least recently used
      one. "Used" means set() or a get() that hit.
    - set() on an existing key replaces the value, restarts its ttl, and makes
      it the most recently used.

    Speed: set() and get() must not scan every entry. The harness does 100,000
    operations against a full cache and gives you a few seconds.

    stats() returns a dict with at least:
        hits, misses     get() calls that found / didn't find a live entry
        evictions        live entries pushed out to make room
        hit_rate         hits / (hits + misses), 0.0 before any get()
    """

    def __init__(self, capacity: int, ttl: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self.ttl = ttl
        self.clock = clock
        self._lock = threading.Lock()  # suggested

    def get(self, key: Hashable, default: Any = None) -> Any:
        raise NotImplementedError

    def set(self, key: Hashable, value: Any, ttl: float | None = None) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def stats(self) -> dict[str, float]:
        raise NotImplementedError
