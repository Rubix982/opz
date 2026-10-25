# Lab 39 · Solution (spoilers)

## The idea

This is the ABD algorithm (Attiya, Bar-Noy and Dolev, 1995): a replicated
register with majority quorums and no leader. Every operation has two phases:

1. **Read phase:** ask everyone for `(value, version)` and wait for a majority.
   Take the newest answer.
2. **Write phase:** store a value on a majority.
   - `put` writes the new value with `(newest_counter + 1, my_id)`.
   - `get` writes back what it's about to return (read repair).

Two majorities of five always share a node, so:
- Any read phase sees the newest acknowledged write, because some node in its
  majority also holds that write.
- The minority side can't complete phase 1, so it never writes anything. Its
  refusals are clean.
- Read repair means that once a read returns version *v*, a majority holds *v*.
  Every later read's majority overlaps it, so reads never go back in time.

## Reference implementation

Replace everything from `# ---- replica` down in `node.py` with:

```python
    # ---------------------------------------------------------------- replica

    def handle(self, method: str, *args: Any) -> Any:
        """Replica side: report what I have, or store a write if it's newer."""
        with self.lock:
            if method == "read":
                (key,) = args
                return self.store.get(key, (None, MISSING))
            if method == "write":
                key, value, version = args
                if tuple(version) > self.store.get(key, (None, MISSING))[1]:
                    self.store[key] = (value, tuple(version))
                return True  # stored, or already had something at least as new
        raise ValueError(f"unknown method {method!r}")

    # ---------------------------------------------------------------- coordinator

    def _ask_everyone(self, method: str, *args: Any) -> list[Any]:
        """Send to every node (this one included); return the answers that came back."""
        answers = []
        for peer in self.cluster:
            try:
                answers.append(self.net.call(self.id, peer, method, *args))
            except Unreachable:
                pass  # down, partitioned away, or the reply was lost: no answer
        return answers

    def _newest(self, key: str) -> tuple[Any, Version]:
        """Phase 1: the newest (value, version) that a majority knows about."""
        answers = self._ask_everyone("read", key)
        if len(answers) < self.majority:
            raise NoQuorum(f"node {self.id}: {len(answers)} of {len(self.cluster)} answered")
        value, version = max(answers, key=lambda a: tuple(a[1]))
        return value, tuple(version)

    def _store_on_majority(self, key: str, value: Any, version: Version) -> None:
        """Phase 2: get (value, version) stored on a majority, or raise NoQuorum."""
        acks = self._ask_everyone("write", key, value, version)
        if len(acks) < self.majority:
            raise NoQuorum(f"node {self.id}: write stored on {len(acks)} of {len(self.cluster)}")

    def put(self, key: str, value: Any) -> Version:
        _, newest = self._newest(key)              # no majority -> NoQuorum, nothing written
        version = (newest[0] + 1, self.id)         # newer than anything a majority has
        self._store_on_majority(key, value, version)
        return version

    def get(self, key: str) -> tuple[Any, Version]:
        value, version = self._newest(key)
        if version != MISSING:
            # Read repair: make sure a majority has what we're about to return,
            # so no later read (whose majority overlaps ours) can see anything older.
            self._store_on_majority(key, value, version)
        return value, version
```

## The three classic mistakes (each one fails a test)

| Mistake | What breaks | Test |
|---|---|---|
| Accept when *any* node answers | the minority side accepts writes; after healing, reads jump back and forth between the two sides' histories | minority-refuses, partition-shapes, reads-go-forward |
| Take the next version from your own copy | a node that was cut off writes with an old counter, and its write silently loses to data it never saw | stale-coordinator, flapping-links |
| No read repair | one reader sees a half-finished write, the next reader's majority doesn't have it, and time goes backwards | reads-go-forward |

## Details worth knowing

- **This is consistency over availability (CP).** During a split, the minority
  side, and everyone during a 2-2-1 split, can do nothing. That's the price.
  etcd, ZooKeeper and Consul (all built on Raft or Zab) make the same choice.
  The extra a leader buys them is ordering many operations, not just a single register.
- **The other choice (AP)** is Dynamo, Cassandra and Riak: both sides accept
  writes, and conflicts are settled later with last-writer-wins (simple, but it
  silently drops one write), version vectors that keep both "siblings" for the
  application to merge, or CRDTs that merge automatically. The checklist line
  also asks for that configuration. A good extension: add a `mode="available"`
  that writes to whoever is reachable, then compare what each mode accepted
  during a split with what survived the heal.
- **"Majority of what?"** Changing the cluster's membership (adding a sixth node)
  is where real systems get hurt. The old and new majorities must overlap, which is
  why Raft has joint consensus. This lab's cluster is fixed.
- **Tunable quorums.** Cassandra's `R + W > N` is the same overlap argument:
  with N=5, writing to W=3 and reading from R=3 overlaps; W=1, R=1 doesn't.
- **Clocks aren't versions.** Using wall-clock timestamps for last-writer-wins
  lets a node with a fast clock win every argument. `(counter, node_id)` needs no clocks.

## What this doesn't cover

- Durability: replicas keep data in memory. A real one writes to disk (and
  fsyncs) before acknowledging, or a restart after a crash forgets acknowledged writes.
- Read-modify-write: two clients doing "read x, write x+1" can still lose an
  update. That needs compare-and-set, or a consensus log (Raft/Paxos, lab 23's lease ideas).
- Real failure detection, timeouts and retries: here an unreachable node fails
  instantly. On a real network you wait, and choosing how long is its own trade-off.
