# Lab 20 · Producer-Consumer with Bounded Buffer

**Time:** ~60 min · **Needs:** Python 3 (standard library only) · **Cost:** free, all local
**Kind:** `[build]`: nothing is broken yet. You build it, and the harness tries to break it.

## The scenario

A log shipper has fast producers (threads reading log files) and slow consumers
(threads sending batches over the network). Between them sits a buffer of
fixed size. If the buffer had no limit, a slow network would let it grow until
the process ran out of memory. With a limit, producers must **wait** when it's
full, and consumers must wait when it's empty.

Getting that waiting right is where it goes wrong: items lost or delivered twice,
threads waiting forever for a wakeup that already happened, CPU burned on
polling. A second classic shows up too. Two threads each take one lock and wait
for the other's, and the program freezes with no error and no CPU use.

## What to build

Everything marked `raise NotImplementedError` in `buffer.py`:

1. **`BoundedBuffer`**: `put(item, timeout=None)`, `get(timeout=None)`,
   `close()`, `len()`. The full contract is in the docstring: FIFO, never more
   than `capacity` items, `Full`/`Empty` on timeout, no busy-waiting, and
   `close()` wakes everyone up.
2. **`transfer(src, dst, amount)`**: move money between two `Account`s while
   holding both their locks. Threads will call it in both directions at once.

## Run the harness

```bash
./check.sh
```

| Test | What it does to your code |
|---|---|
| basics | FIFO order, capacity, and that `put`/`get` with a timeout really wait, then give up |
| stress | 6 producers × 4,000 items, 6 consumers (some slow), capacity 8, with Python made to switch threads very often. Checks nothing is lost, nothing is doubled, and the buffer never holds more than 8 |
| close | `close()` while threads are blocked in `put()` and in `get()`: they must wake and raise `Closed`, and items already in the buffer must still drain |
| no-busy-wait | measures the CPU a blocked `get()` uses in 1.5 s |
| transfer-deadlock | 80,000 transfers, A→B and B→A at the same time, with a deadline |

Each test runs in its own process with a deadline, so a deadlock shows up as a
`FAIL … hung` line instead of freezing your terminal.

## Hints (one at a time)

1. `threading.Condition` is a lock plus a waiting room. You can make **two**
   conditions share **one** lock: "not full" for producers, "not empty" for consumers.
2. `cond.wait()` can return when the thing you waited for is *still not true*:
   another thread got there first, or the wakeup was spurious. What does that
   mean for `if full: wait()`?
3. `cond.wait_for(predicate, timeout)` does the loop for you and returns whether
   the predicate came true.
4. After `close()`, which waiting threads need waking, and with `notify()` or `notify_all()`?
5. Transfer: if thread 1 locks A then B, and thread 2 locks B then A, each can end
   up holding one lock and waiting forever for the other. Is there an order *every*
   thread could agree on, whatever direction the money moves?

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why `while` and not `if` around `wait()`:
- Why two conditions on one lock, instead of one condition or two locks:
- What happened (or would) with polling + `sleep` instead of waiting:
- The four conditions for deadlock, and which one lock ordering removes:
- What a bounded buffer does for the system as a whole (backpressure):
