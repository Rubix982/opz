# Lab 20 · Solution (spoilers)

## The buffer

```python
class BoundedBuffer:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._items: deque[Any] = deque()
        self._lock = threading.Lock()
        self._not_full = threading.Condition(self._lock)
        self._not_empty = threading.Condition(self._lock)
        self._closed = False

    def put(self, item: Any, timeout: float | None = None) -> None:
        with self._not_full:
            ok = self._not_full.wait_for(
                lambda: self._closed or len(self._items) < self.capacity, timeout)
            if self._closed:
                raise Closed
            if not ok:
                raise Full
            self._items.append(item)
            self._not_empty.notify()

    def get(self, timeout: float | None = None) -> Any:
        with self._not_empty:
            self._not_empty.wait_for(lambda: self._items or self._closed, timeout)
            if self._items:
                item = self._items.popleft()
                self._not_full.notify()
                return item
            if self._closed:
                raise Closed
            raise Empty

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._not_full.notify_all()
            self._not_empty.notify_all()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
```

Why each part is there:

- **One lock, two conditions.** The deque and the `closed` flag are one piece of
  state, so one lock protects them. Two conditions let a `put` wake only a
  *consumer* (`notify` on `not_empty`) instead of every waiting thread.
- **`wait_for`, i.e. a `while` loop.** Being woken only means "something
  changed". By the time this thread gets the lock back, another consumer may
  have taken the item. With `if empty: wait()` the thread carries on and pops
  from an empty deque. With a broken `put`, the buffer goes over capacity. The
  harness's stress test catches both.
- **`notify()` vs `notify_all()`.** One item frees one slot, so waking one waiter
  is enough. `close()` changes things for *everybody*, so it wakes everybody.
- **`get` checks items before `closed`**, so closing doesn't throw away work
  that's already buffered.
- **No polling.** A waiting thread is parked by the OS and uses no CPU. A
  `sleep(0.001)` loop uses CPU *and* adds latency.

## The transfer

```python
def transfer(src: Account, dst: Account, amount: int) -> None:
    first, second = (src, dst) if src.id < dst.id else (dst, src)
    with first.lock, second.lock:
        src.balance -= amount
        dst.balance += amount
```

Deadlock needs four things at once: mutual exclusion, hold-and-wait, no
preemption, and a **circular wait**. Taking locks in one global order (here, by
account id) makes a cycle impossible: everyone climbs the same ladder, so
nobody holds a higher lock while waiting for a lower one. Whichever direction
the money moves, the locks are taken in the same order.

## Details worth knowing

- **`queue.Queue` is exactly this** (with `maxsize`), built the same way: one
  mutex, conditions `not_empty`/`not_full`/`all_tasks_done`. It has
  `shutdown()` from Python 3.13. Use it in real code; build it once to know what's in it.
- **Backpressure** is the system-level point. A bounded buffer turns "consumers are
  slow" into "producers slow down", instead of "memory grows until the OOM killer
  arrives" (lab 05). Unbounded queues hide overload until it's fatal.
- **Lock ordering doesn't scale to unknown lock sets.** When you can't know all
  the locks up front (a database), systems detect deadlocks instead (a wait-for
  graph, then abort one transaction) or use `try_lock` with a timeout and back off.
- **What this doesn't cover:** multiple *processes* or machines. There the buffer is
  a broker (Kafka, RabbitMQ, SQS), "never lost, never doubled" gets much harder
  (B5's exactly-once lab), and the locks become a distributed lock service (B1).
