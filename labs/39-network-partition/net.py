"""A fake network for lab 39. Given: you don't need to change it.

Nodes live in one process and call each other with net.call(src, dst, method,
*args), which runs dst.handle(method, *args) and returns its result, unless the
network says no. The harness controls the network:

    net.partition({0, 1}, {2, 3, 4})   # two groups that can't reach each other
    net.heal()                         # everyone can reach everyone again
    net.drop_rate = 0.1                # 10% of requests, or of replies, are lost
    net.delay = (0.0, 0.005)           # each call takes a random 0-5 ms

A node can always reach itself. A lost REPLY is the nasty case: dst.handle()
ran, so the change happened over there, but the caller gets Unreachable and
can't tell whether it did.
"""

import copy
import random
import threading
import time
from typing import Any, Protocol


class Unreachable(Exception):
    """The request or the reply was lost: the caller can't know which."""


class Handler(Protocol):
    id: int

    def handle(self, method: str, *args: Any) -> Any: ...


class Network:
    def __init__(self, seed: int = 0):
        self.nodes: dict[int, Handler] = {}
        self.drop_rate = 0.0
        self.delay: tuple[float, float] = (0.0, 0.0)
        self.calls = 0
        self._groups: list[set[int]] | None = None
        self._lock = threading.Lock()
        self._rng = random.Random(seed)

    def register(self, node: Handler) -> None:
        self.nodes[node.id] = node

    # -- what the harness controls ------------------------------------------

    def partition(self, *groups: set[int]) -> None:
        """Split the cluster: nodes can only reach nodes in their own group."""
        with self._lock:
            self._groups = [set(g) for g in groups]

    def heal(self) -> None:
        with self._lock:
            self._groups = None

    def reachable(self, src: int, dst: int) -> bool:
        with self._lock:
            return self._reachable(src, dst)

    def _reachable(self, src: int, dst: int) -> bool:
        if src == dst or self._groups is None:
            return True
        return any(src in g and dst in g for g in self._groups)

    # -- what nodes use -------------------------------------------------------

    def call(self, src: int, dst: int, method: str, *args: Any) -> Any:
        """Run nodes[dst].handle(method, *args) on behalf of src.

        Raises Unreachable if dst can't be reached, or if the request or the reply
        is dropped. Arguments and results are copied, as if they had crossed a
        wire: nodes never share Python objects.
        """
        with self._lock:
            self.calls += 1
            lost_request = src != dst and self._rng.random() < self.drop_rate
            lost_reply = src != dst and self._rng.random() < self.drop_rate
            wait = self._rng.uniform(*self.delay) if src != dst else 0.0
        if wait:
            time.sleep(wait)
        if lost_request or not self.reachable(src, dst):
            raise Unreachable(f"{src} -> {dst}")
        result = self.nodes[dst].handle(method, *copy.deepcopy(args))
        if lost_reply or not self.reachable(dst, src):
            raise Unreachable(f"reply {dst} -> {src} lost")
        return copy.deepcopy(result)
