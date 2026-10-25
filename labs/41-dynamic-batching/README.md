# Lab 41 · Batching

**Time:** ~60 min · **Needs:** Python 3 (standard library only) · **Cost:** free, all local
**Kind:** `[build]`: nothing is broken yet. You build it, and the harness tries to break it.

## The scenario

A small model sits behind an endpoint, and the server calls it once per request.
With one user that's fine. With ten users at once, the tenth waits for the nine
before it: one request's latency is ~25 ms, the tenth one's is ~250 ms. Meanwhile
most of every model call is fixed cost that has nothing to do with how many
inputs it carries.

`model.py` is a stand-in with that cost structure, so no downloads are needed:
one call at a time, 20 ms of fixed overhead per call plus 1 ms per item. Sixteen
requests in one call cost 36 ms; sixteen calls cost 336 ms.

**Dynamic batching** fixes it: hold each request for a few milliseconds, collect
whatever else arrives, and send them through the model together. The catch is
the wait. Hold too long and a lone user pays for a batch that never fills.

## What to build

Everything marked `raise NotImplementedError` in `batcher.py`, a `Batcher` with:

- `submit(item, timeout)`: blocks until *this caller's* answer is ready.
- a worker thread that takes the oldest request, collects more until it has
  `max_batch_size` **or** `max_wait_ms` has passed, then makes one `predict()` call.
- **isolation:** `model.predict` fails the whole call if any input is bad
  (`BadInput.index` says which). The bad request's caller gets `BadInput`;
  everyone else in that batch still gets their answer.
- **backpressure:** `submit()` raises `QueueFull` immediately when `max_queue`
  requests are already waiting. `pending()` reports how many are.
- `close()`: refuse new requests (`Closed`), finish accepted ones, stop the worker.

The contract is in the docstrings. Don't edit `model.py`.

## Run the harness

```bash
./check.sh
```

| Test | What it does |
|---|---|
| basics | single requests come back right |
| routing | 48 threads × 25 requests; each caller must get its own answer, and batching must actually happen |
| bad-item | waves of 20 simultaneous requests with 3 bad ones |
| load | 10 users, batched vs one-request-per-call on the same model: needs 2.5× the throughput and a lower p95; writes both to `results.txt` |
| low-load | one user alone: p95 may be at most ~30 ms worse than unbatched |
| backpressure | 60 callers flood a queue of 8 in front of a slow model |
| shutdown | `close()` with requests in flight |

Each test runs in its own process with a deadline, so a hang shows up as a FAIL.

## Hints, one at a time

1. Each request needs somewhere to put its answer and a way to wake its caller.
   A small object holding the item, a `threading.Event`, and a result/error slot does it.
2. One `threading.Condition` around a `deque` is enough for the queue. The worker
   waits on it; `submit()` notifies it.
3. Measure `max_wait` from when the **oldest** request in the batch arrived, not
   from when the worker started looking. Otherwise a request that already waited
   behind a model call waits again.
4. Answers come back in input order. Pair them with the requests you sent, and
   be careful if you change the list after a failure.
5. After `BadInput`, you can fail that one request and retry the rest. There may
   be another bad item in "the rest".
6. `close()` has to wake a worker that is waiting on an empty queue.

## Retro (fill in)

- Throughput and p95 at ten users, before and after (from `results.txt`):
- Why one call with 16 items is cheaper than 16 calls:
- What `max_wait_ms` trades, and what a lone user pays for it:
- How one bad input was kept from failing its whole batch:
- Why rejecting with `QueueFull` beats an unbounded queue:
