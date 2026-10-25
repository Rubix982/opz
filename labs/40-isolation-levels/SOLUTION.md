# Lab 40 · Solution (spoilers)

## Bug 1: lost update (booking)

```
T1: SELECT seats_left → 1          T2: SELECT seats_left → 1
T1: UPDATE seats_left = 0          T2: UPDATE ... (waits for T1's row lock)
T1: COMMIT                         T2: UPDATE seats_left = 0   ← computed from a stale read
                                   T2: COMMIT
```

Both bookings succeed, and seats_left says 0. The second write overwrote the first,
because the new value was computed in Python from a value read *earlier*.

**Fix:** let the database check and decrement in one statement:

```python
row = conn.execute(
    "UPDATE events SET seats_left = seats_left - 1 WHERE id = %s AND seats_left > 0 RETURNING seats_left",
    (event_id,),
).fetchone()
if row is None:
    raise SoldOut()
```

At READ COMMITTED, T2's UPDATE waits for T1's row lock, then **re-evaluates the
WHERE clause against the new row**. `seats_left > 0` is now false, so 0 rows
are updated and the buyer is told "sold out". No isolation change, no retries.

(`SELECT ... FOR UPDATE` then UPDATE also works: it takes the row lock at read time.)

## Bug 2: write skew (rota)

```
T1: count on call → 2              T2: count on call → 2
T1: UPDATE alice off               T2: UPDATE bob off        ← different rows, no conflict
T1: COMMIT                         T2: COMMIT                → 0 on call
```

Each transaction kept the rule against what it read, but each read went stale
because of the *other's* write to a *different* row. Row locks can't see that.

- **REPEATABLE READ isn't enough** in Postgres. It gives each transaction a
  snapshot (no non-repeatable reads, no phantoms), but write skew is allowed.
  Both still commit.
- **SERIALIZABLE** (SSI) tracks read/write dependencies. It sees that T1 read
  what T2 wrote, and vice versa, and aborts one with `SerializationFailure`.
- **The aborted one must be retried.** On retry it reads count = 1 and refuses
  with a clean 409.

```python
def retry_serializable(fn, attempts: int = 10):
    for attempt in range(attempts):
        try:
            with connect(serializable=True) as conn:
                with conn.transaction():
                    return fn(conn)
        except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected):
            if attempt == attempts - 1:
                raise
            time.sleep(random.uniform(0, 0.01 * 2 ** attempt))
```

The whole transaction is retried, reads included. Retrying only the failed
statement would reuse stale reads.

## The half-fix check.sh catches

Setting SERIALIZABLE everywhere **without a retry** fixes both invariants, and
hands hundreds of users a 500 under load. Correct but unusable.

## Details worth knowing

- **Alternatives for write skew:** lock the rows the rule depends on
  (`SELECT ... FROM doctors WHERE shift = %s FOR UPDATE`), or make the rule a
  constraint (e.g. a per-shift counter row that both transactions must update,
  which turns write skew into an ordinary row conflict).
- **Retries need idempotent side effects.** Anything outside the database
  (an email, a payment call) inside the retried block runs again. Do it after
  commit, or make it idempotent (lab 06's event IDs).
- **Deadlocks** are retried the same way. Two transactions locking the same
  rows in opposite order deadlock; Postgres kills one after `deadlock_timeout`.
  Locking in a consistent order avoids most of them.
- **Phantoms:** at READ COMMITTED a second `SELECT count(*)` in the same
  transaction can see rows inserted meanwhile. REPEATABLE READ stops that.
- **What this lab doesn't cover:** distributed transactions across services
  (no single database to serialize them), and read replicas, which can serve
  data behind the primary whatever your isolation level.
