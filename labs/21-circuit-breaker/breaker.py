"""Lab 21: a circuit breaker.

Build everything marked `raise NotImplementedError`. Standard library only.
The harness (`./check.sh`) imports this file, gives it a fake clock, and wraps
a dependency that is healthy, then slow and failing, then healthy again.
"""

import threading
import time
from typing import Any, Callable


class CircuitOpen(Exception):
    """The call was refused without trying: the breaker is open."""


class CircuitBreaker:
    """Stops calling a dependency that keeps failing, and checks back later.

    States, as the strings "closed", "open" and "half_open":

    - closed: calls go through. Each failure (the function raised) adds one to
      a count of *consecutive* failures; any success resets it to zero. When
      the count reaches `failure_threshold`, the breaker opens.
    - open: calls are refused straight away, without touching the dependency,
      until `reset_timeout` seconds (by `clock()`) have passed since it opened.
    - half_open: the first call after the timeout is let through as a single
      trial. While that trial is running, every other call is refused. If the
      trial succeeds the breaker closes (count back to zero). If it fails the
      breaker opens again, and the timeout starts over from now.

    A refused call returns `fallback()` if a fallback was given, otherwise it
    raises CircuitOpen. A call that goes through and fails returns `fallback()`
    if given, otherwise re-raises the original exception.

    It's used from many threads at once.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.clock = clock
        self._lock = threading.Lock()  # suggested

    @property
    def state(self) -> str:
        """The current state: "closed", "open" or "half_open".

        It's fine for this to still say "open" after the timeout has passed;
        the move to half_open can happen on the next call.
        """
        raise NotImplementedError

    def call(self, fn: Callable[..., Any], *args: Any,
             fallback: Callable[[], Any] | None = None, **kwargs: Any) -> Any:
        """Call fn(*args, **kwargs) through the breaker."""
        raise NotImplementedError
