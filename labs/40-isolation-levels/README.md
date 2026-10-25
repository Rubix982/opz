# Lab 40 · Transaction Isolation Levels Simulation

**Time:** ~60 min · **Needs:** Docker Compose, Python 3 · **Cost:** free, all local

## The incident

Two complaints in one week from the clinic:

- The flu-shot clinic had 5 seats and **20 people** got a confirmation email.
- Both doctors on Saturday's shift asked to go off call within the same second,
  each one was told "fine, the other one is covering", and **nobody** was on call.

Every query is inside a transaction. Each request checks the rule before it
writes. Nothing in the logs is an error.

## Setup

```bash
./setup.sh                          # Postgres + the clinic API on localhost:8040
python3 tools/race.py book          # 20 buyers, 5 seats, all at once
python3 tools/race.py off-call      # alice and bob, same shift, same moment
curl -s localhost:8040/state
```

`tools/race.py` takes `--trials N`. Races don't happen every time, so run a few.
Re-run `./setup.sh` after every change to `app/app.py`.

## Your job

1. **Explain both bugs before fixing anything.** Read `book()` and `go_off_call()`
   in `app/app.py`. Hints, one at a time if you're stuck:
   - Postgres's default isolation level is READ COMMITTED: each *statement*
     sees data committed before *it* started, not before the transaction started.
   - Booking: two transactions read `seats_left = 1`, both compute `0`, both write `0`.
     What happened to one of the decrements? (This one is called a **lost update**.)
   - Rota: the two transactions update *different rows* (alice's, bob's). Neither
     sees the other's write, and no row is written twice. Why doesn't a row lock help?
     (This one is called **write skew**.)
   - `docker compose exec db psql -U clinic` and try it by hand in two sessions:
     `BEGIN ISOLATION LEVEL ...;` in each, then interleave the statements.
2. **Fix both** in `app/app.py`:
   - The booking can be made safe without changing the isolation level. Can the
     check and the write be one statement?
   - The rota needs a stronger isolation level. Try REPEATABLE READ first and
     see whether it's enough. Then SERIALIZABLE.
   - SERIALIZABLE doesn't block conflicts, it *aborts* one transaction
     (`SerializationFailure`, SQLSTATE 40001). What must the app do then, so the
     user never sees it?
3. **Prove it.** `./check.sh` builds your app as a separate stack on port 18040
   and passes only when no event is oversold, every shift keeps someone on call,
   no request gets a 500, and a busy round still finishes quickly.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Lost update: what interleaving causes it, and the one-statement fix:
- Write skew: why no row is written twice, yet the rule breaks:
- What REPEATABLE READ prevents in Postgres, and what it doesn't:
- What SERIALIZABLE does on a conflict, and what the app owes it:
- When I'd use `SELECT ... FOR UPDATE` instead:
