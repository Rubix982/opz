"""Your job queue. Build this.

A durable, at-least-once job queue stored in one SQLite file, so any number of
worker *processes* can share it and a crash loses nothing. Standard library only.

The contract (check.sh tests all of it):
- enqueue() returns only once the job is safely on disk. Kill the process right
  after, and the job is still there when the queue is reopened.
- reserve() hands a job to exactly one worker and hides it from everyone else for
  `visibility_timeout` seconds. Two workers must never hold the same job at once.
- ack() marks the job done, but only with the receipt from the *current*
  reservation. A worker whose time ran out (the job was handed to someone else)
  gets False and changes nothing.
- A job not acked in time becomes visible again and is delivered again (that's
  the "at least once").
- A job delivered `max_attempts` times without an ack goes to the dead-letter
  list instead of being delivered again.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Reserved:
    job_id: int
    payload: str
    attempt: int   # 1 on first delivery, 2 on the next, ...
    receipt: str   # proves which reservation an ack belongs to


class JobQueue:
    def __init__(self, path: str, visibility_timeout: float = 1.0, max_attempts: int = 3) -> None:
        """Open (or create) the queue stored at `path`."""
        raise NotImplementedError

    def enqueue(self, payload: str) -> int:
        """Add a job; return its id. Durable when this returns."""
        raise NotImplementedError

    def reserve(self, worker_id: str) -> Reserved | None:
        """Hand the oldest visible job to this worker, or return None if there is none."""
        raise NotImplementedError

    def ack(self, job_id: int, receipt: str) -> bool:
        """Mark the job done if `receipt` is from its current reservation. Return whether it was."""
        raise NotImplementedError

    def dead_letters(self) -> list[tuple[int, str, int]]:
        """Jobs given up on, as (job_id, payload, attempts)."""
        raise NotImplementedError

    def counts(self) -> dict[str, int]:
        """{"ready": jobs waiting or in flight, "done": acked jobs, "dead": dead letters}."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
