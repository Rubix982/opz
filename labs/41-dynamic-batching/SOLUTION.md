# Lab 41 · Solution (spoilers)

## The idea

Model calls here cost `20 ms + 1 ms × items`, one at a time. Ten users calling
one-by-one get ~40 req/s and a p95 near 270 ms, because each request waits for
everyone ahead of it. Batched, those ten requests share one 30 ms call: about
250 req/s and a p95 near 45 ms. On this M2:

```
one request per call :    39.7 req/s   p95  275.8 ms
dynamic batching     :   253.7 req/s   p95   41.8 ms   (avg batch 10.0)
```

## Reference implementation

```python
import threading
import time
from collections import deque

from model import BadInput, Model


class QueueFull(Exception):
    """Too many requests waiting; the caller should back off and retry."""


class Closed(Exception):
    """The batcher has been closed."""


class _Request:
    __slots__ = ("item", "arrived", "done", "result", "error")

    def __init__(self, item: str):
        self.item = item
        self.arrived = time.monotonic()
        self.done = threading.Event()
        self.result: str | None = None
        self.error: BaseException | None = None


class Batcher:
    def __init__(self, model: Model, max_batch_size: int = 16, max_wait_ms: float = 5.0,
                 max_queue: int = 256):
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_wait = max_wait_ms / 1000
        self.max_queue = max_queue
        self._queue: deque[_Request] = deque()
        self._cond = threading.Condition()
        self._closed = False
        self._worker = threading.Thread(target=self._run, name="batcher", daemon=True)
        self._worker.start()

    def submit(self, item: str, timeout: float | None = 10.0) -> str:
        req = _Request(item)
        with self._cond:
            if self._closed:
                raise Closed("batcher is closed")
            if len(self._queue) >= self.max_queue:
                raise QueueFull(f"{len(self._queue)} requests already waiting")
            self._queue.append(req)
            self._cond.notify()
        if not req.done.wait(timeout):
            raise TimeoutError(f"no answer within {timeout}s")
        if req.error is not None:
            raise req.error
        return req.result  # type: ignore[return-value]

    def pending(self) -> int:
        with self._cond:
            return len(self._queue)

    def close(self, timeout: float = 10.0) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        self._worker.join(timeout)

    # -- worker ------------------------------------------------------------

    def _next_batch(self) -> list[_Request] | None:
        with self._cond:
            while not self._queue:
                if self._closed:
                    return None
                self._cond.wait()
            # The deadline counts from when the oldest request arrived, so a
            # request that already waited behind a model call isn't held longer.
            deadline = self._queue[0].arrived + self.max_wait
            while len(self._queue) < self.max_batch_size and not self._closed:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cond.wait(left)
            n = min(self.max_batch_size, len(self._queue))
            return [self._queue.popleft() for _ in range(n)]

    def _run(self) -> None:
        while (batch := self._next_batch()) is not None:
            self._serve(batch)

    def _serve(self, batch: list[_Request]) -> None:
        try:
            outputs = self.model.predict([r.item for r in batch])
        except BadInput as e:
            # Only the bad item fails; run the rest again without it.
            bad = batch[e.index]
            bad.error = e
            bad.done.set()
            rest = batch[: e.index] + batch[e.index + 1:]
            if rest:
                self._serve(rest)
            return
        except Exception as e:  # noqa: BLE001 - anything else fails the whole batch
            for r in batch:
                r.error = e
                r.done.set()
            return
        for r, out in zip(batch, outputs):
            r.result = out
            r.done.set()
```

## What each piece is for

- **`_Request` with an `Event`.** Every caller waits on its own event, and the
  worker fills that request's own slot, so answers can't cross. Routing by
  "position in some list" is how answers end up with the wrong caller: one
  removed or reordered item shifts everything after it.
- **Deadline from the oldest arrival.** Under load the queue fills while the
  previous call runs, so the next batch goes out at once, full. With one user the
  request waits at most `max_wait_ms` (5 ms) before going alone.
- **Isolation by retry.** On `BadInput`, fail that request and re-run the rest.
  Recursion handles a second bad item. Cost: one extra call per bad item. The
  alternative is validating inputs before batching, which is cheaper if
  validation is cheap.
- **Bounded queue, immediate rejection.** `QueueFull` lets the caller (or a load
  balancer) back off or try another replica. An unbounded queue turns overload
  into ever-growing memory and latency, and every request times out at once.
- **`close()`.** Set `_closed`, `notify_all()` so a waiting worker wakes up, drain
  what's queued, and join the thread.

## Details worth knowing

- **This is what real servers do.** vLLM, TGI and Triton all batch dynamically.
  LLM servers go further with *continuous batching*: requests join and leave a
  running batch between tokens, because answers finish at different lengths.
- **Bigger batches aren't free.** Per-item cost and memory grow with the batch,
  and the slowest item sets the pace. `max_batch_size` caps that.
- **Pick `max_wait_ms` from the latency budget.** If the target p95 is 100 ms and
  a call takes 40 ms, waiting 5–10 ms is cheap. Waiting 50 ms isn't.
- **What this doesn't cover:** multiple model replicas (one batcher each, or a
  shared queue), priorities (a batch-of-one for interactive traffic), per-request
  deadlines (drop requests whose caller already gave up), and padding costs when
  items have different lengths (real batchers group by length).
