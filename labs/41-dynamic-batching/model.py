"""A stand-in for a small model served on one CPU. Given, don't edit.

It behaves like real inference where it matters for batching:
- One call at a time. There's one copy of the model and one device, so calls
  queue behind a lock, exactly as they would on one process.
- Every call pays a fixed overhead (moving weights through cache, kernel
  launches, Python glue) plus a small cost per item. So one call with 16 items
  is far cheaper than 16 calls with one item each.
- The output depends only on the input, so the harness can check that every
  caller got its *own* answer.
- One bad input fails the whole call, like a real batch whose tensor can't be
  built. `BadInput.index` says which item it was.
"""

import hashlib
import threading
import time

OVERHEAD_S = 0.020   # per call
PER_ITEM_S = 0.001   # per item in the call
MAX_ITEMS = 64       # the most one call accepts


class BadInput(ValueError):
    """An input the model can't handle. `index` is its position in the call."""

    def __init__(self, index: int, item: str):
        super().__init__(f"bad input at position {index}: {item!r}")
        self.index = index
        self.item = item


def expected(item: str) -> str:
    """What the model returns for one item. The harness uses it to check answers."""
    return hashlib.sha256(item.encode()).hexdigest()[:12]


def is_bad(item: str) -> bool:
    return not isinstance(item, str) or item.startswith("!")


class Model:
    def __init__(self, overhead_s: float = OVERHEAD_S, per_item_s: float = PER_ITEM_S):
        self.overhead_s = overhead_s
        self.per_item_s = per_item_s
        self._device = threading.Lock()
        self.calls = 0
        self.items = 0
        self.batch_sizes: list[int] = []

    def predict(self, items: list[str]) -> list[str]:
        """Run the model on a batch. Returns one output per item, in the same order.

        Raises BadInput if any item is bad (and none of the batch is returned),
        ValueError if the batch is empty or larger than MAX_ITEMS.
        """
        if not items or len(items) > MAX_ITEMS:
            raise ValueError(f"batch size must be 1..{MAX_ITEMS}, got {len(items)}")
        with self._device:
            time.sleep(self.overhead_s + self.per_item_s * len(items))
            self.calls += 1
            self.items += len(items)
            self.batch_sizes.append(len(items))
            for i, item in enumerate(items):
                if is_bad(item):
                    raise BadInput(i, item)
            return [expected(item) for item in items]
