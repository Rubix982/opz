# Lab 22 · Cache with Expiration & Eviction

**Time:** ~60 min · **Needs:** Python 3 (standard library only) · **Cost:** free, all local
**Kind:** `[build]`: nothing is broken yet. You build it, and the harness tries to break it.

## The scenario

An API caches user profiles in memory for 60 seconds. Traffic grows, the set of
users grows, and two bugs show up together:

- **Memory climbs all day.** Entries expire, but nothing removes them: expiry is
  only checked when someone reads that exact key again, and most keys are never
  read again.
- **A fix makes it worse.** Someone adds a size cap with LRU eviction, and now
  live, popular entries get evicted while thousands of dead ones sit in memory
  taking up the slots.

## What to build

`TTLCache` in `cache.py`: `get`, `set`, `len`, `stats`. The full contract is in
the docstring. In short:
- Never return an expired entry, including at the exact moment it expires.
- Never hold more than `capacity` entries.
- When full, drop expired entries before evicting a live one. If you must evict
  a live one, evict the least recently used.
- Expired entries must actually leave memory, not just stop being returned.
- Fast: no scanning every entry on each call.
- Thread-safe, with hit/miss/eviction counts and a hit rate.

It takes a `clock` argument so the harness can jump time forward. Always use
`self.clock()`.

## Run the harness

```bash
./check.sh
```

| Test | What it does to your code |
|---|---|
| basics / expiry | set, get, overwrite; an entry read at exactly set-time + ttl must be gone |
| lru-order | fills the cache, uses some keys, checks the right one is evicted |
| expired-first | a full cache where the *most recently used* entry has expired: it must go before a live one |
| no-lingering | 1,000 entries, time jumps forward, one `set()`: only live entries may remain in memory |
| overload | 100,000 random operations on a 5,000-entry cache with mixed ttls, checking every answer against the truth, within 8 s |
| stats | a scripted sequence with known hits, misses and evictions |
| threads | 8 threads × 15,000 operations, with Python switching threads constantly |

## Hints (one at a time)

1. `collections.OrderedDict` gives you LRU nearly for free: `move_to_end(key)`
   on use, and `popitem(last=False)` takes the oldest.
2. LRU order and expiry order are *different* orders. An entry used a second ago
   can expire first. One structure can't answer both "least recently used?" and
   "what expires next?" quickly.
3. "What expires next?" is a priority-queue question. Look at `heapq`.
4. When a key is overwritten, its old expiry time is still in the heap. You
   don't have to remove it then. How could you recognise it as stale when it
   eventually comes out?
5. Which method should clean up expired entries so memory stays bounded,
   without scanning everything?

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Lazy vs. active expiry, and what each one costs:
- Why LRU order and expiry order need two structures:
- How stale heap entries are handled, and what keeps the heap itself from growing forever:
- What the hit rate told me about this workload, and what would raise it:
- Where a real cache (Redis, memcached, Caffeine) makes different choices:
