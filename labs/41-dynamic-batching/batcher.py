"""Dynamic batching in front of one model. Fill in everything marked
NotImplementedError. Standard library only (threading, queue, time...).

Callers arrive one request at a time, from many threads. Instead of calling the
model once per request, collect requests for a moment and send them together:

- A worker thread takes the first waiting request, then keeps collecting until
  it has `max_batch_size` requests OR `max_wait_ms` has passed since that first
  request arrived, whichever comes first. Then it makes ONE model.predict() call.
- Every caller gets back the answer for its own input, never someone else's.
- One bad input must not fail the other requests in its batch. Its caller gets
  the model's BadInput exception; everyone else gets their answer.
- The waiting line is bounded. When `max_queue` requests are already waiting,
  submit() raises QueueFull immediately instead of letting memory grow.
- close() stops new work (submit() then raises Closed), lets everything already
  accepted finish, and stops the worker thread.
"""

from model import Model


class QueueFull(Exception):
    """Too many requests waiting; the caller should back off and retry."""


class Closed(Exception):
    """The batcher has been closed."""


class Batcher:
    def __init__(self, model: Model, max_batch_size: int = 16, max_wait_ms: float = 5.0,
                 max_queue: int = 256):
        """Start the worker thread. `max_batch_size` is at most model.MAX_ITEMS."""
        raise NotImplementedError

    def submit(self, item: str, timeout: float | None = 10.0) -> str:
        """Queue one request, block until its answer is ready, and return it.

        Raises QueueFull at once if max_queue requests are already waiting,
        Closed if close() has been called, the model's BadInput if this item is
        bad, and TimeoutError if no answer arrives within `timeout` seconds.
        """
        raise NotImplementedError

    def pending(self) -> int:
        """How many accepted requests are waiting to go into a batch right now."""
        raise NotImplementedError

    def close(self, timeout: float = 10.0) -> None:
        """Refuse new requests, finish the accepted ones, stop the worker."""
        raise NotImplementedError
