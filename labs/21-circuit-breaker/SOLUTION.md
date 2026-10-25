# Lab 21 · Solution (spoilers)

## The implementation

```python
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.clock = clock
        self._lock = threading.Lock()
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._trial_running = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def _admit(self) -> bool:
        """Decide, under the lock, whether this call may reach the dependency."""
        with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open" and self.clock() - self._opened_at >= self.reset_timeout:
                self._state = "half_open"
            if self._state == "half_open" and not self._trial_running:
                self._trial_running = True
                return True
            return False

    def _record(self, ok: bool) -> None:
        with self._lock:
            if self._state == "half_open":
                self._trial_running = False
                if ok:
                    self._state, self._failures = "closed", 0
                else:
                    self._state, self._opened_at = "open", self.clock()
            elif ok:
                self._failures = 0
            else:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._state, self._opened_at = "open", self.clock()

    def call(self, fn: Callable[..., Any], *args: Any,
             fallback: Callable[[], Any] | None = None, **kwargs: Any) -> Any:
        if not self._admit():
            if fallback is not None:
                return fallback()
            raise CircuitOpen("circuit open")
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record(ok=False)
            if fallback is not None:
                return fallback()
            raise
        self._record(ok=True)
        return result
```

## Why it's built this way

- **Decide → call → record.** `_admit()` decides under the lock, the call runs
  *without* the lock, and `_record()` updates under the lock. Holding the lock
  during the call would make every caller wait behind a slow dependency, which
  is the exact failure the breaker exists to stop.
- **`open → half_open` happens lazily**, when a call arrives after the timeout.
  There's no background timer to manage or stop.
- **The single trial is a flag checked and set in the same critical section.**
  The check ("no trial running") and the claim ("now I'm the trial") must be
  atomic, or 50 threads all pass the check before any of them sets the flag. The
  thundering-herd test catches the version without the flag: 50 of 50 callers
  hit a dependency that is barely back on its feet.
- **A failed trial resets `_opened_at`**, so the next trial is a full timeout away.
  Without that, a dead dependency would get a trial on every call.
- **Fallback is the caller's choice.** The breaker refuses, and the caller says
  what "refused" should mean: an empty list, a cached value, or an error.

## Details worth knowing

- **Consecutive-failure counting is the simplest trigger, not the best.** At high
  traffic, real breakers (resilience4j, Polly, Envoy's outlier detection) use a
  failure *rate* over a sliding window with a minimum number of calls, so one
  success among 99 failures doesn't reset everything.
- **Slowness should count as failure.** The breaker only sees exceptions, so the
  client must have a timeout. With no timeout, a hung call never fails and never
  trips the breaker. Some breakers also count "slower than X" calls as failures.
- **One breaker per dependency (or per host),** not one global one. Otherwise
  recommendations being down opens the breaker for payments too.
- **Breakers and retries interact.** Retrying a failing call 3 times triples the
  load on a struggling service. Put retries *inside* the breaker's view, and stop
  retrying once it's open.
- **What this doesn't cover:** sharing state across processes. Each replica of
  checkout has its own breaker, and each one discovers the outage on its own.
  That's usually fine, since it needs no coordination. Also: bulkheads, a
  separate worker pool per dependency, which stop a slow dependency eating all
  the threads even before the breaker opens.
