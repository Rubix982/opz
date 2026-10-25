# Lab 39 · Network Partition Simulation

**Time:** ~2 hours · **Needs:** Python 3 (standard library only) · **Cost:** free, all local
**Kind:** `[build]`: nothing is broken yet. You build it, and the harness tries to break it.

## The scenario

A config store runs on five nodes for safety. One afternoon a switch fails, and
the cluster splits: two nodes can see each other, and the other three can see each
other, but the two groups can't talk. Both halves keep accepting writes. When
the switch comes back, half the changes made that afternoon are gone, and
nobody can say which.

This is the CAP trade-off made concrete. During a partition you choose:
- **consistency:** the side that can't prove it's the majority refuses, or
- **availability:** both sides answer, and you reconcile conflicts later.

This lab builds the consistent choice: a store where only a majority can act, so
the two sides can never both accept a write.

## What to build

Everything marked `raise NotImplementedError` in `node.py`. The fake network
(`net.py`) is given. The harness uses it to cut links, lose messages and add delay.

1. **`handle(method, *args)`**: the replica side. Report a key's
   `(value, version)`, and store a write only if its version is newer.
2. **`put(key, value)`**: find the newest version a majority has, write
   `(counter + 1, my_id)` to a majority, and return that version. If a majority
   can't be reached, raise `NoQuorum`.
3. **`get(key)`**: the newest `(value, version)` a majority knows. A later read
   through any node must never return something older.

Versions are tuples `(counter, node_id)` and compare as tuples, so two nodes that
pick the same counter at the same time are still ordered.

## Run the harness

```bash
./check.sh                     # everything (about 15 seconds)
./check.sh partition-shapes    # one test
```

| Test | What it does to your cluster |
|---|---|
| basics | put and get through different nodes; versions go up; missing keys |
| minority-refuses | a 2 \| 3 split, then a 1 \| 4 split: the small side must refuse reads and writes, the big side must keep going, and after healing no refused write may appear |
| no-majority | a 2 \| 2 \| 1 split: nobody has a majority, so everything is refused; then it heals |
| stale-coordinator | node 4 misses five writes, then coordinates one: its write must win, not lose to the old data |
| partition-shapes | five split shapes in turn, with every node reading and writing: counts acknowledged writes on each side and checks none is lost after healing |
| reads-go-forward | partitions shifting every 120 ms, 5% of messages lost, one writer, four readers: no read may return something older than an earlier acknowledged write or an earlier read |
| flapping-links | links changing every few ms, 15% of messages lost, 400 operations: each must return or refuse within 2s, and the cluster must be consistent and working afterwards |

## Hints (one at a time)

1. "Majority" means a majority of the *whole* cluster (3 of 5), not of the nodes
   you can currently reach. A node can't tell "the others are down" from "I'm cut
   off". That's the whole problem.
2. Two majorities of the same cluster always share at least one node. Every
   guarantee here comes from that overlap.
3. Don't send a write anywhere until you know a majority answered your read.
   Otherwise a refused write can be left on a few replicas, and appear later.
4. Your own copy may be stale: you might be the node that was cut off. Take the
   newest version from the majority's answers, not from your own store.
5. A lost reply means the write may have happened even though you got
   `Unreachable`. That's fine: you just don't count it as an acknowledgement.
6. If `reads-go-forward` fails with "after another read had already seen", look
   at a write that reached only one replica of your majority before failing.
   One reader sees it, the next reader's majority doesn't. What could the first
   reader do before returning?

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why a node can't tell "they're down" from "I'm cut off":
- Why majorities make the two sides unable to both accept a write:
- What the version `(counter, node_id)` protects against:
- Why reads also write (read repair), and what goes wrong without it:
- What this store gives up during a partition, and which systems choose the other side:
