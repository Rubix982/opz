"""check.sh's test harness: runs clusters of your nodes and injects failures."""

import sys
import time
from collections import defaultdict

from cluster import TTL, Coordinator, NodeRunner, Storage
from node import Node

failures = 0


def report(ok: bool, msg: str) -> None:
    global failures
    print(("pass  " if ok else "FAIL  ") + msg, flush=True)
    failures += 0 if ok else 1


def believes_leader(node: Node) -> bool:
    try:
        return bool(node.is_leader)
    except Exception:
        return False


class Cluster:
    def __init__(self, n: int = 3) -> None:
        self.coordinator, self.storage = Coordinator(), Storage()
        self.nodes = {f"n{i}": Node(f"n{i}", self.coordinator, self.storage) for i in range(1, n + 1)}
        self.runners = {nid: NodeRunner(node) for nid, node in self.nodes.items()}
        for r in self.runners.values():
            r.start()

    def leaders(self, exclude: set[str] = frozenset()) -> list[str]:
        return [nid for nid, node in self.nodes.items()
                if self.runners[nid].alive and nid not in exclude and believes_leader(node)]

    def wait_leader(self, timeout: float, exclude: set[str] = frozenset()) -> str | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            got = self.leaders(exclude)
            if len(got) == 1:
                return got[0]
            time.sleep(0.02)
        return None

    def accepted(self, node_id: str | None = None, after: float = 0.0) -> list:
        return [w for w in self.storage.log if w.accepted and w.at > after
                and (node_id is None or w.node_id == node_id)]

    def errors(self) -> str:
        errs = {e for r in self.runners.values() for e in r.errors}
        return "; ".join(sorted(errs))[:200]

    def stop(self) -> None:
        for r in self.runners.values():
            r.kill()


def one_term_one_node(cluster: Cluster) -> list[str]:
    owners: dict[int, set[str]] = defaultdict(set)
    for w in cluster.accepted():
        owners[w.token].add(w.node_id)
    return [f"term {t}: {sorted(n)}" for t, n in owners.items() if len(n) > 1]


def scenario_election_and_failover() -> None:
    c = Cluster()
    leader = c.wait_leader(3.0)
    if leader is None:
        report(False, f"no single leader within 3s (errors: {c.errors() or 'none'})")
        c.stop()
        return
    report(True, f"one leader elected ({leader})")

    # Steady state: one leader the whole time, and it keeps writing.
    start, max_seen, changed = time.monotonic(), 0, False
    for _ in range(40):
        got = c.leaders()
        max_seen = max(max_seen, len(got))
        changed |= got not in ([leader], [])
        time.sleep(0.05)
    progress = len(c.accepted(leader, after=start))
    report(max_seen == 1 and not changed and progress >= 10,
           f"steady for 2s: at most one leader, no flapping, {progress} writes accepted")

    # Kill the leader: someone else takes over within TTL + 1.5s.
    killed_at = time.monotonic()
    c.runners[leader].kill()
    new = c.wait_leader(TTL + 1.5, exclude={leader})
    took = time.monotonic() - killed_at
    if new:
        time.sleep(0.3)
        report(len(c.accepted(new, after=killed_at)) > 0,
               f"leader killed; {new} took over in {took:.1f}s and is writing")
    else:
        report(False, f"leader killed; no new leader within {TTL + 1.5:.1f}s")

    bad = one_term_one_node(c)
    report(not bad, "every term's writes came from a single node" + (f": {bad}" if bad else ""))
    c.stop()


def scenario_gc_pause(trial: int) -> None:
    c = Cluster()
    old = c.wait_leader(3.0)
    if old is None:
        report(False, f"pause trial {trial}: no leader to pause (errors: {c.errors() or 'none'})")
        c.stop()
        return
    pause = 3 * TTL
    c.storage.pause_next_write(old, pause)
    paused_at = time.monotonic()

    new = c.wait_leader(TTL + 1.5, exclude={old})
    if new is None:
        report(False, f"pause trial {trial}: {old} frozen, but no one else took over")
        c.stop()
        return

    resume = paused_at + pause
    time.sleep(max(0.0, resume - time.monotonic()) + 0.6)
    late = [w for w in c.storage.log if w.node_id == old and w.at >= resume - 0.05]
    stale_refused = bool(late) and not late[0].accepted
    stepped_down = not believes_leader(c.nodes[old])
    new_writing = len(c.accepted(new, after=resume)) > 0
    old_accepted_after = [w for w in late if w.accepted]

    report(stale_refused and not old_accepted_after,
           f"pause trial {trial}: {old}'s write from before the pause was refused when it landed"
           + ("" if late else " (it never landed)")
           + (f" (but {len(old_accepted_after)} stale writes were accepted)" if old_accepted_after else ""))
    report(stepped_down and new_writing,
           f"pause trial {trial}: {old} stepped down; {new} kept writing")
    bad = one_term_one_node(c)
    report(not bad, f"pause trial {trial}: every term's writes came from a single node"
           + (f": {bad}" if bad else ""))
    c.stop()


def main() -> int:
    scenario_election_and_failover()
    for trial in (1, 2, 3):
        scenario_gc_pause(trial)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
