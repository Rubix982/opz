# Lab 23 · Leader Election in a Cluster

**Track B, build it** · **Time:** ~60 min · **Needs:** Python 3 (standard library only)

## The scenario

Three replicas of a service run at once, but only one may do the work: write to
the shared database, run the nightly job, send the emails. If two do it at the same
time you get double charges and corrupted data. If none do, nothing happens.

So the replicas elect a leader through a lease service (what etcd, ZooKeeper or
Consul provide), and the leader keeps renewing its lease. Then the hard case: the
leader **freezes** after checking its lease and before its write lands. That might
be a long GC pause, a frozen VM, or a slow disk. Meanwhile its lease runs out and
someone else takes over. When the old leader wakes up, it still thinks it's in
charge and finishes its write.

## What you build

`node.py`: the `Node` class. Everything else is given in `cluster.py` (don't edit it):

| Piece | What it gives you |
|---|---|
| `Coordinator.try_acquire(node_id)` | A `Lease(term, expires_at)` if nobody holds a live one, else `None`. Every grant has a higher `term`. |
| `Coordinator.renew(node_id, term)` | A fresh `Lease` if you still hold it, else `None`. |
| `Storage.write(node_id, token, value)` | Stores the write, or raises `StaleTokenError` if `token` is lower than one it has seen. |
| `NodeRunner` | Calls your `node.tick(now)` every 50 ms. `now` is the coordinator's clock. TTL is 1 second. |

**The contract** (`check.sh` tests all of it):
1. At most one node believes it's leader at a time, and it stays leader while healthy.
2. If the leader dies, another node takes over within about TTL + 1 second.
3. Every write carries a **fencing token**, so storage can refuse a write from a
   leader that's been replaced.
4. A node whose write is refused stops acting as leader.

## Your job

1. Read `cluster.py` once, then fill in `node.py`.
2. Run `./check.sh` (~25 s). It runs a cluster of three, watches the steady
   state, kills the leader, then three times freezes the leader **inside**
   a write for 3 seconds and checks what happens when it wakes up.
3. Hints, one at a time if you're stuck:
   - Start with a node that only acquires and writes. Watch check.sh fail
     "at most one leader", and work out why.
   - A lease is only as good as your last successful renew. When should a leader
     stop acting, *before* the coordinator tells it?
   - The node can check its lease right before writing and still be wrong when
     the write lands. No check inside the node can close that gap. Who can?
   - Which number in a `Lease` can only go up, and where should it travel?
4. **Write the retro** (below).

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why "check the lease, then write" isn't safe on its own:
- What a fencing token is, and who has to check it:
- Why the token must come from the coordinator and not from the node:
- What the safety margin before lease expiry protects against:
- What this lab's coordinator hides that a real one (etcd, ZooKeeper) has to solve:
