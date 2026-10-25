# Lab 24 · Build a Job Queue from Scratch

**Track B, build it** · **Time:** ~60–90 min · **Needs:** Python 3 (standard library only)

## The scenario

Your service hands slow work (resizing images, sending emails, charging cards) to
background workers through a queue. Workers crash. Machines reboot. A malformed
job crashes every worker that touches it. Through all of it, the business wants
three things: **no job lost**, **no job stuck forever**, and as few duplicate
runs as possible.

SQS, RabbitMQ, Sidekiq and Celery all solve this the same basic way. You'll build
that core yourself in one SQLite file shared by several worker processes.

## What you build

`jobqueue.py`: the `JobQueue` class. Its docstrings are the contract:

| Method | Promise |
|---|---|
| `enqueue(payload) -> id` | Durable when it returns, even if the process is `kill -9`'d right after. |
| `reserve(worker_id) -> Reserved \| None` | Gives the oldest visible job to **one** worker and hides it for `visibility_timeout` seconds. |
| `ack(job_id, receipt) -> bool` | Marks it done, but only with the receipt from the **current** reservation. |
| redelivery | A job not acked in time becomes visible again: attempt 2, 3, … |
| `dead_letters()` | A job delivered `max_attempts` times without an ack is parked here instead. |

`worker.py` is given: it takes jobs, "works" (a short sleep), acks, and logs every
step. Jobs whose payload is `poison` crash it every time.

## Your job

1. Fill in `jobqueue.py`.
2. Run `./check.sh`. First unit checks: durability under `kill -9`, visibility
   timeout, receipts, dead letters. Once those pass comes the chaos run: 4 worker
   processes, 80 jobs and 3 poison ones, workers killed at random, then all at once.
   It passes only if nothing is lost, poison ends up in dead letters, no job is
   ever held by two workers at once, and nothing acked runs again.
3. Hints, one at a time if you're stuck:
   - Store a job's state, attempt count and "invisible until" time in the row
     itself. Then a reservation is just an UPDATE, and crashing never loses it.
   - Why does `ack` need a receipt, not just the job id? Picture worker A being
     slow, its time running out, and worker B getting the same job.
   - If the chaos run says a job was held by two workers at once, look at the gap
     between "find a free job" and "claim it". Read about SQLite's `BEGIN IMMEDIATE`.
   - `sqlite3.connect(..., isolation_level=None)` stops Python from opening
     transactions behind your back, so you control exactly where they start.
4. **Write the retro** (below).

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- What "at least once" promises, and what it doesn't:
- Why the visibility timeout must be longer than the slowest job:
- What the receipt prevents (the race in one sentence):
- Where the race between workers was, and what closed it:
- Why a consumer of an at-least-once queue must be idempotent:
