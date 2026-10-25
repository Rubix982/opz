"""A replicated key-value store that stays correct through network partitions.
Lab 39: you build the parts marked TODO.

Every node is two things at once:
  * a REPLICA: it stores (value, version) per key and answers other nodes' calls
    through handle();
  * a COORDINATOR: clients call put()/get() on any node, and that node talks to
    the replicas (itself included) through net.call() to do the operation.

The guarantee (consistency over availability, "CP"):
  * put() returns only once a MAJORITY of all nodes has stored the write. If it
    can't reach a majority it raises NoQuorum.
  * get() returns the newest value a majority knows about, and never a value
    older than one a previous put() or get() already returned. No majority ->
    NoQuorum.
  * So the minority side of a partition refuses everything, the majority side
    keeps working, and nothing acknowledged is ever lost.

Versions are tuples (counter, node_id) and compare as tuples, so two nodes
writing the same counter are still ordered. MISSING is the version of a key
nobody has written.
"""

import threading
from typing import Any

from net import Network, Unreachable  # noqa: F401  (you'll need Unreachable)

Version = tuple[int, int]
MISSING: Version = (0, -1)


class NoQuorum(Exception):
    """Couldn't reach a majority of the cluster; the operation may or may not have happened."""


class Node:
    def __init__(self, node_id: int, cluster: list[int], net: Network):
        self.id = node_id
        self.cluster = list(cluster)          # every node id, this one included
        self.majority = len(cluster) // 2 + 1
        self.net = net
        self.store: dict[str, tuple[Any, Version]] = {}  # the replica's data
        self.lock = threading.Lock()                    # handle() runs on many threads at once
        net.register(self)

    # ---------------------------------------------------------------- replica

    def handle(self, method: str, *args: Any) -> Any:
        """Answer a call from a coordinator (possibly this node itself).

        Design the messages yourself. You'll need at least:
          "read",  key                  -> this replica's (value, version) for key,
                                           or (None, MISSING)
          "write", key, value, version  -> store it ONLY if version is newer than
                                           what this replica has; return something
                                           that tells the caller it's stored

        Many threads call this at once: hold self.lock while you touch self.store.
        Raise ValueError for an unknown method.
        """
        raise NotImplementedError

    # ---------------------------------------------------------------- coordinator

    def put(self, key: str, value: Any) -> Version:
        """Write value under key; return the version it was written with.

        Must:
          * pick a version newer than any version a MAJORITY has for this key
            (not just newer than this node's own copy: this node may have been
            cut off and be far behind);
          * get the write stored on a majority (this node counts) before returning;
          * raise NoQuorum if either step can't reach a majority. Don't store the
            write anywhere until you know you can do the first step.

        net.call() raises Unreachable for a node you can't reach (or a lost
        reply); count it as "no answer" and carry on with the others.
        """
        raise NotImplementedError

    def get(self, key: str) -> tuple[Any, Version]:
        """Return (value, version) for key, or (None, MISSING) if never written.

        Must ask a MAJORITY and return the newest (value, version) among their
        answers, and must make sure that a later get() through ANY node can't
        return something older than what this call returns (hint: what if only
        one replica in your majority has the newest version?).
        Raises NoQuorum if a majority can't be reached.
        """
        raise NotImplementedError
