# Lab 28 · Solution (spoilers)

## What was wrong

Four separate failures, all hidden by the same habits:

| Night | What happened | Why it looked green |
|---|---|---|
| Empty export | 0 rows in, 0 rows out, totals file with just a header | No exception, so nothing "failed" |
| Corrupted | Half the rows skipped by `except: continue`, totals ~half | Bad rows were silently dropped |
| Renamed column | Every row raised `KeyError`, all skipped, empty output | Same `continue` |
| Crash mid-write | `orders_clean.csv` truncated at 100 rows | The files were written in place |

And in every case `finally:` wrote `status: success` and `last_success: now`, then
`sys.exit(0)`. The scheduler, the dashboard and the freshness alert all believed it.

## The fix

**1. Fail loudly.** Any exception, or any validation failure: write a *failed*
status, print a clear message, `sys.exit(1)`. The exit code is the contract with
whatever runs the job; it's what retries, alerts and downstream dependencies key on.

**2. Validate the data, not just the process.** An exception only covers the
failures the code happens to trip over. Check what "right" looks like:

```python
REQUIRED = {"order_id", "region", "amount_cents", "status"}
MIN_PAID_ROWS = 500          # a normal night has ~1,000
MAX_BAD_FRACTION = 0.005     # tolerate a stray row, not half the file

missing = REQUIRED - set(reader.fieldnames or [])
if missing:
    raise ValidationError(f"export is missing columns {sorted(missing)}")
...  # parse strictly; count rows with non-positive or unparseable amounts, unknown regions
if len(bad) / total > MAX_BAD_FRACTION:
    raise ValidationError(f"{len(bad)} of {total} rows invalid (first at line {bad[0]})")
if len(orders) < MIN_PAID_ROWS:
    raise ValidationError(f"only {len(orders)} paid orders, expected at least {MIN_PAID_ROWS}")
```

**3. Write atomically.** Build each output in a temp file **in the same
directory**, `fsync`, then `os.replace(tmp, final)`. A rename within one
filesystem is atomic: readers see the old file or the new one, never half. Build
*both* outputs before replacing either, so the two never disagree.

```python
fd, tmp = tempfile.mkstemp(dir=OUT_DIR, prefix=".tmp-")
with os.fdopen(fd, "w", newline="") as f:
    write_rows(f)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, os.path.join(OUT_DIR, "orders_clean.csv"))
```

**4. `last_success` means success.** Update it only after validation passes and
the outputs are in place. On failure, record `status: failed`, `last_run` and the
error, and keep the old `last_success`. Then the freshness alert, "no good run in
26 hours", fires on its own, *even if the job never ran at all* (the scheduler
was down, the cron line was deleted). That last case is why freshness alerts
exist: a job that never runs can't report its own failure.

A complete fixed `job/nightly_revenue.py` passes `check.sh`:

```
pass  good night: exit 0, totals correct
pass  empty export               failed loudly (exit 1), good output untouched
pass  corrupted amounts          failed loudly (exit 1), good output untouched
pass  upstream renamed column    failed loudly (exit 1), good output untouched
pass  crash mid-write            failed loudly (exit 137), good output untouched
pass  freshness alert fires 28h after the last good run
pass  recovery run: exit 0, new totals, alert clears
LAB PASSED
```

## Details worth knowing

- **Thresholds should come from history**, not a constant: "at least 50% of the
  7-day median row count" adapts as the business grows. Tools like Great
  Expectations, dbt tests and Soda do this declaratively.
- **Leaving the old output in place is a choice.** Downstream now reads
  yesterday's numbers as if they were today's. That's better than wrong numbers,
  but only safe if consumers check freshness too, or the output carries its own
  date (`as_of` column, dated file names).
- **Crash leftovers:** a killed run can leave a `.tmp-*` file behind. Clean old
  temp files at startup.
- **What this doesn't catch:** data that is plausible but wrong. Prices in
  dollars instead of cents, or a duplicate day, pass every check above.
  Distribution checks (today's total within 3σ of the last 30 days) and
  reconciliation against another source catch some of it. Nothing catches all of it.
