"""A worker process (given; don't edit). Takes jobs from the queue until told to stop.

Each job's work is a short sleep. A job whose payload is "poison" crashes the
worker every time, the way a malformed message crashes a real consumer.

Every step is appended to the events log so the harness can check the contract:
    start <job_id> <worker> <attempt> <time>
    done  <job_id> <worker>
    acked <job_id> <worker> <True|False>
"""

import os
import sys
import time

from jobqueue import JobQueue

db, worker_id, events, vt, work = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
q = JobQueue(db, visibility_timeout=vt)


def log(line: str) -> None:
    with open(events, "a") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


while not os.path.exists(events + ".stop"):
    job = q.reserve(worker_id)
    if job is None:
        time.sleep(0.02)
        continue
    log(f"start {job.job_id} {worker_id} {job.attempt} {time.time():.4f}")
    if job.payload == "poison":
        os._exit(3)
    time.sleep(work)
    log(f"done {job.job_id} {worker_id}")
    log(f"acked {job.job_id} {worker_id} {q.ack(job.job_id, job.receipt)}")
