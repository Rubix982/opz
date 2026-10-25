# Lab 42 · Model Speed vs Accuracy

**Time:** ~45 min · **Needs:** Python 3 (standard library only) · **Cost:** free, all local
**Kind:** `[design]`: nothing to break. You write a one-page decision, and
`check.sh` checks it holds up against the numbers.

## The scenario

A support widget drafts an answer while the customer watches. It runs the most
accurate model available, `large-fp32`: accuracy 0.952, but p95 latency is 2.1
seconds, and the session data says customers abandon the widget after about one
second. It also costs $2.10 per 1,000 requests.

The team benchmarked alternatives (`data/benchmarks.csv`): smaller models,
int8/int4 quantization, a distilled model, dynamic batching, and a router that
sends easy questions to a small model and escalates the rest.

**The constraints (agreed, not negotiable):**

| | target | why |
|---|---|---|
| latency | **p95 ≤ 300 ms** for the model call | the 1 s budget minus retrieval and rendering |
| accuracy | **≥ 0.90** on the labelled support set | below that, support staff rewrite drafts more than they save |
| cost | **≤ $0.40 per 1,000 requests** | the feature's budget |

**Traffic:** about 5 requests/second on average (~430k a day), peaks of 12/s.

## Your job

1. Read `data/benchmarks.csv`. Columns: p50/p95 latency in ms, accuracy (0–1),
   cost in USD per 1,000 requests.
2. Fill in `DECISION.md`: every section, no "Replace this" lines left.
3. Fill in `decision.json`. It's JSON rather than YAML, so the check needs only
   Python's standard library. It holds the chosen variant, its p95, accuracy and
   cost (copied from the CSV), and at least two **measurable** revisit triggers.
4. Run `./check.sh`. It checks that:
   - the choice exists and meets every constraint
   - your numbers match the benchmarks
   - every section is written, and the constraints are stated with their numbers
   - at least two options are compared, with numbers
   - each revisit trigger contains a number
   - no other option that also meets the constraints is at least as good on all
     three axes (p95, accuracy, cost). If one is, you can still choose yours,
     but DECISION.md needs a `## Why not <that variant>` section.

The check can't tell whether your reasoning is *good*, only whether it's complete
and consistent with the data. Compare yours with `SOLUTION.md` afterwards.

## Hints, one at a time

1. Cross out everything that breaks a hard constraint first. Then compare only
   what's left.
2. Which column did you sort by? A great p50 can hide a terrible p95.
3. Of the survivors, is any one at least as good as another on *all three*
   axes? That other one is out.
4. More than one option will survive. Margin is a legitimate reason to choose:
   how far is each from the line it must not cross?
5. "Revisit if accuracy drops" isn't measurable. Below what, measured how, for how long?

## Retro (fill in)

- What I chose, and the one number that decided it:
- What I gave up, in numbers:
- Which option looked best at first glance, and why it was wrong:
- What would make me change my mind:
