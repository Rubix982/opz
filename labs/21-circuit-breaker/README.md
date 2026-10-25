# Lab 21 · Circuit Breaker Implementation

**Time:** ~60 min · **Needs:** Python 3 (standard library only) · **Cost:** free, all local
**Kind:** `[build]`: nothing is broken yet. You build it, and the harness tries to break it.

## The scenario

The checkout service calls a recommendations service to fill a "you might also
like" box. One afternoon recommendations gets slow: every call hangs until the
5-second client timeout. Checkout's worker threads all end up stuck waiting on
it, and checkout stops answering, *including requests that never needed
recommendations*. A non-essential dependency took down an essential service.

A circuit breaker sits between the two. When the dependency keeps failing, it
stops calling it for a while and answers straight away with a fallback (an empty
box). Every so often it lets one request through to see if things recovered.

## What to build

`CircuitBreaker` in `breaker.py`: a `state` property and
`call(fn, *args, fallback=None, **kwargs)`. The full contract is in the docstring:

```
         failures reach threshold                 timeout passed
closed ─────────────────────────────▶ open ─────────────────────────▶ half_open
  ▲                                     ▲                                │
  │            trial succeeded          │      trial failed              │
  └─────────────────────────────────────┼────────────────────────────────┘
                                        └──── (timer starts over) ◀──────┘
```

It takes a `clock` argument so the harness can move time by hand instead of
waiting 30 real seconds. Always use `self.clock()`, never `time.time()`.

## Run the harness

```bash
./check.sh
```

| Test | What it does to your code |
|---|---|
| closed | healthy and failing calls; the failure count must be *consecutive* |
| opens | 5 failures, then 100 calls: the dependency must not be touched until the timeout |
| half-open | after the timeout exactly one trial; a failed trial restarts the timer; a good one closes |
| thundering-herd | 50 threads call at once just after the timeout, while the trial hangs: 1 may try, 49 get the fallback straight away |
| slow-dependency | 200 calls while every call takes 0.1 s and then times out: must finish in under 2 s; then recovery |

## Hints (one at a time)

1. Write the transitions as a table first: for each state, what happens on a call,
   a success and a failure.
2. When does `open` become `half_open`? Nothing ticks in the background, so check
   it when a call arrives.
3. The thundering-herd test: 50 threads all see "timeout passed" at the same
   moment. What stops all 50 from deciding they are the trial? What has to be
   checked *and* set while holding one lock?
4. Don't hold the lock while calling the dependency. A trial that hangs for
   5 seconds would block every other caller, which defeats the point. Decide under
   the lock, call outside it, record the result under the lock again.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- What failure the breaker is really protecting against (hint: not the dependency's):
- Why "consecutive" failures, and what a rate over a window would do better:
- Why half-open allows only one trial:
- What a good fallback looks like for a few real dependencies (and when there isn't one):
- Breaker vs. retries (lab B2's backoff): how they fight, and how they work together:
