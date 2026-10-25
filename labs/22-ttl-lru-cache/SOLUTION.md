# Lab 22 · Solution (spoilers)

## The idea

Two orders, two structures:

- **Recency** for eviction: an `OrderedDict`, least recently used first.
  `move_to_end` on every hit or set, `popitem(last=False)` to evict.
- **Expiry time** for cleanup: a min-heap of `(expires_at, seq, key)`.
  The soonest expiry is always on top, so `set()` pops everything already expired
  in O(k log n) for the k expired entries, without touching the live ones.

An overwritten key leaves its old heap item behind. Instead of searching the
heap to delete it (O(n)), it's skipped when it comes out: if the entry's
current `expires_at` doesn't match the popped one, the item is stale. That's
"lazy deletion". To stop stale items piling up when hot keys are overwritten
constantly, the heap is rebuilt once it grows past a few times the capacity.

## The implementation

```python
import heapq
import itertools
import threading
import time
from collections import OrderedDict
...

class TTLCache:
    def __init__(self, capacity: int, ttl: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self.ttl = ttl
        self.clock = clock
        self._lock = threading.Lock()
        # key -> (value, expires_at); order = recency, least recently used first
        self._entries: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()
        # (expires_at, seq, key): soonest expiry on top. Overwrites leave stale
        # heap items behind; they're skipped when popped.
        self._expiry: list[tuple[float, int, Hashable]] = []
        self._seq = itertools.count()
        self._hits = self._misses = self._evictions = self._expirations = 0

    def _purge_expired(self, now: float) -> None:
        heap = self._expiry
        while heap and heap[0][0] <= now:
            expires_at, _, key = heapq.heappop(heap)
            entry = self._entries.get(key)
            if entry is not None and entry[1] == expires_at:
                del self._entries[key]
                self._expirations += 1
        # Stale heap items (from overwrites) are bounded by rebuilding now and then.
        if len(heap) > 4 * self.capacity + 64:
            self._expiry = [(exp, next(self._seq), k) for k, (_, exp) in self._entries.items()]
            heapq.heapify(self._expiry)

    def get(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or self.clock() >= entry[1]:
                self._misses += 1
                return default
            self._entries.move_to_end(key)
            self._hits += 1
            return entry[0]

    def set(self, key: Hashable, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            now = self.clock()
            self._purge_expired(now)
            expires_at = now + (self.ttl if ttl is None else ttl)
            self._entries[key] = (value, expires_at)
            self._entries.move_to_end(key)
            heapq.heappush(self._expiry, (expires_at, next(self._seq), key))
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
                self._evictions += 1

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def stats(self) -> dict[str, float]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "expirations": self._expirations,
                "hit_rate": self._hits / total if total else 0.0,
            }
```

Why each part matters:

- **`get` checks `clock() >= expires_at` itself.** It doesn't rely on cleanup
  having run, so nothing expired is ever returned, even between `set()` calls.
- **`set` purges before inserting.** That gives "expired entries go first": by
  the time the capacity check runs, the dead entries are already gone. It also
  gives "no lingering": every write cleans up.
- **One lock around everything.** The dict, the heap and the counters change
  together. The harness's thread test, run without the lock, crashes with
  `OrderedDict mutated during iteration` or `KeyError`. Lost counter updates show
  up too: `hits + misses` stops matching the number of gets.
- **`seq` in the heap tuple** breaks ties between equal expiry times, so `heapq`
  never has to compare two keys (which might not be comparable).

## Details worth knowing

- **Lazy + periodic active expiry is what Redis does:** check on access, plus a
  background job that samples random keys with a TTL and deletes the expired
  ones, repeating while more than 25% of the sample was expired. That's
  probabilistic, not a heap, because a heap over millions of keys costs memory.
- **LRU isn't the only policy.** LFU keeps popular keys through a burst of
  one-off reads. W-TinyLFU (Caffeine, Ristretto) mixes both and usually wins.
  A one-time scan of many keys flushes a plain LRU cache completely.
- **Capacity by count isn't capacity by bytes.** 5,000 small entries and 5,000
  large ones use very different amounts of memory. Real caches often bound by
  size (memcached's slabs, Caffeine's weigher).
- **Thundering herd on expiry:** a hot key expires and 500 requests all miss and
  hit the database at once. Fixes: one request refills while the others wait
  (request coalescing), or refresh shortly *before* expiry.
- **What this doesn't cover:** a cache shared by many processes or machines
  (B3's distributed cache), invalidation when the source data changes, and
  negative caching (remembering that something doesn't exist).
