# Lab 28 · Silent Job Failures

**Time:** ~40 min · **Needs:** Python 3 (standard library only) · **Cost:** free, all local

## The incident

Finance's weekly revenue deck says the business made **$0** on Wednesday and
less than half the usual on Thursday. The ops dashboard has shown the nightly
revenue job **green every night**. Three downstream reports read its output, and
all of them were wrong for days before a human noticed.

Nobody was paged, because nothing "failed".

## Setup

```bash
python3 job/nightly_revenue.py fixtures/orders-2026-10-21.csv   # a normal night
python3 tools/dashboard.py                                      # what ops sees
cat out/revenue_by_region.csv
python3 tools/freshness.py                                      # the "is it stale?" alert
```

The upstream exports in `fixtures/` are what the job actually received:

| File | What upstream sent |
|---|---|
| `orders-2026-10-20.csv`, `-21.csv` | normal nights |
| `orders-2026-10-22-empty.csv` | an empty export: their query returned no rows |
| `orders-2026-10-22-corrupt.csv` | half the amounts negative or blank |
| `orders-2026-10-22-renamed.csv` | they renamed `amount_cents` to `amount` |

Run the job on each one and look at the exit code (`echo $?`), the output files
and the dashboard after each. `JOB_CRASH_AFTER_ROWS=100 python3 job/...` makes
the job die mid-write, like an out-of-memory kill or a reboot would.

## Your job

1. **Break it first.** For each bad export: what exit code, what's in `out/`,
   what does the dashboard say? Which outputs would a downstream report happily read?
2. **Fix `job/nightly_revenue.py`.** Hints, one at a time if you're stuck:
   - `except Exception: print(...)` followed by `sys.exit(0)`. What is the
     scheduler (cron, Airflow, Kubernetes) going to conclude?
   - The empty export raises no exception at all. Exceptions are only one kind of
     failure. What would you check about the *output* before calling it good?
     Think: required columns, row counts, value ranges.
   - After the crash, what's in `orders_clean.csv`? How can you write a file so
     readers only ever see the old version or the complete new one, never half?
     (Look up `os.replace`.)
   - The `finally:` block writes `last_success` on every run. What should the
     freshness alert be measuring?
   - Don't touch `job/faults.py` or `tools/`. They're the test hook and the monitoring.
3. **Prove it.** `./check.sh` plays a week of nights against your job in a scratch
   folder: a good one, the four bad ones, then a recovery run.
4. **Write the retro** (below).

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why "exit 0" was the most damaging line in the job:
- The checks I added on the data, and the failure each one catches:
- How the write became all-or-nothing, and why that matters to readers:
- What `last_success` must mean for the freshness alert to work:
- What still slips through (hint: plausible but wrong data):
