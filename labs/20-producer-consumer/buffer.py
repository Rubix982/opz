"""Lab 20: a bounded blocking buffer, and a two-lock transfer.

Build everything marked `raise NotImplementedError`. Standard library only.
The harness (`./check.sh`) imports this file and attacks it with threads.
"""

import threading
from collections import deque
from typing import Any


class Full(Exception):
    """put() gave up: the buffer stayed full for the whole timeout."""


class Empty(Exception):
    """get() gave up: the buffer stayed empty for the whole timeout."""


class Closed(Exception):
    """The buffer was closed: no more puts, and gets have drained it."""


class BoundedBuffer:
    """A FIFO buffer holding at most `capacity` items, shared by many threads.

    Contract:
    - put(item) blocks while the buffer is full. With a timeout, raises Full if
      it is still full when the timeout runs out.
    - get() blocks while the buffer is empty. With a timeout, raises Empty if it
      is still empty when the timeout runs out. Items come out in FIFO order.
    - Waiting must not burn CPU: no `while full: sleep(0.001)` loops.
    - len(buf) is the number of items held right now, never more than capacity.
    - close(): after it, put() raises Closed straight away. get() keeps returning
      the items still held, then raises Closed once the buffer is empty. Every
      thread blocked in put() or get() wakes up and reacts to the close
      (blocked puts raise Closed; blocked gets raise Closed if nothing is left).
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        # Suggested building blocks; use them or not.
        self._items: deque[Any] = deque()
        self._lock = threading.Lock()

    def put(self, item: Any, timeout: float | None = None) -> None:
        raise NotImplementedError

    def get(self, timeout: float | None = None) -> Any:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError


class Account:
    """A bank account guarded by its own lock. Provided; don't change it."""

    _next_id = 0

    def __init__(self, balance: int) -> None:
        self.balance = balance
        self.lock = threading.Lock()
        Account._next_id += 1
        self.id = Account._next_id


def transfer(src: Account, dst: Account, amount: int) -> None:
    """Move `amount` from src to dst, holding BOTH accounts' locks while you do.

    Many threads call this at once, some moving A -> B while others move B -> A.
    It must never deadlock, and money must never be created or destroyed.
    (Overdrafts are allowed; don't worry about negative balances.)
    """
    raise NotImplementedError
