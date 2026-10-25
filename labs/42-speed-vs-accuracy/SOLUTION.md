# Lab 42 · Solution (spoilers)

There's more than one defensible answer. This is one worked decision, then the
common mistakes.

## Step 1: cross out what breaks a constraint

| variant | p95 ms | accuracy | $/1k | |
|---|---|---|---|---|
| large-fp32 | 2100 | 0.952 | 2.10 | ✗ latency, cost |
| large-int8 | 980 | 0.946 | 0.95 | ✗ latency, cost |
| medium-fp16 | 420 | 0.931 | 0.42 | ✗ latency, cost |
| router-small-large | 1100 | 0.938 | 0.36 | ✗ latency (p50 is 60 ms!) |
| small-fp32 | 120 | 0.874 | 0.09 | ✗ accuracy |
| small-int8 | 70 | 0.861 | 0.05 | ✗ accuracy |
| medium-int8 | 230 | 0.924 | 0.21 | ✓ |
| medium-int8-b8 | 290 | 0.924 | 0.12 | ✓ |
| medium-int4 | 160 | 0.901 | 0.14 | ✓ but dominated |
| distilled-small-int8 | 75 | 0.902 | 0.06 | ✓ |

## Step 2: drop what's dominated

`distilled-small-int8` beats `medium-int4` on all three axes (75 vs 160 ms,
0.902 vs 0.901, $0.06 vs $0.14), so int4 is out. Three remain, each best at
something: distilled-small-int8 (fastest, cheapest), medium-int8 (accuracy with
latency headroom), medium-int8-b8 (accuracy, cheaper, little headroom).

## Step 3: choose on margin

The worked decision (`DECISION.md` + `decision.json` below) picks **medium-int8**:
- distilled-small-int8 is 0.002 above the accuracy floor, less than the
  benchmark's own noise.
- medium-int8-b8 is 10 ms under the latency target, and batching latency grows
  exactly when traffic spikes.
- medium-int8 costs ~$39/day more than the batched one at 430k requests/day,
  bought as 70 ms of headroom.

Picking medium-int8-b8 with a plan (e.g. cap batch wait, alarm at 270 ms) or
distilled-small-int8 with a stronger accuracy-monitoring plan is also defensible.
What matters is that the record says what was given up.

### DECISION.md

    # Decision: which model serves the support-answer endpoint
    
    ## Context
    
    The support widget drafts an answer while the customer watches. Today it runs
    large-fp32: accurate (0.952), but p95 is 2,100 ms and session data shows customers
    abandon the widget after about one second. It also costs $2.10 per 1,000 requests.
    
    ## Constraints
    
    - **Latency:** p95 ≤ 300 ms end to end for the model call (the widget's 1 s budget
      minus retrieval and rendering). p95, not average: the slow tail is who leaves.
    - **Accuracy:** ≥ 0.90 on the labelled support set. Below that, the support team's
      review found drafts needed rewriting more often than they saved time.
    - **Cost:** ≤ $0.40 per 1,000 requests, the budget finance agreed for this feature.
    
    ## Options considered
    
    | variant | p95 ms | accuracy | $/1k | verdict |
    |---|---|---|---|---|
    | large-fp32 | 2100 | 0.952 | 2.10 | fails latency and cost |
    | large-int8 | 980 | 0.946 | 0.95 | fails latency and cost |
    | medium-fp16 | 420 | 0.931 | 0.42 | fails latency and cost (just) |
    | router-small-large | 1100 | 0.938 | 0.36 | great p50 (60 ms), but the escalated 15% blow the p95 |
    | medium-int8 | 230 | 0.924 | 0.21 | meets all three |
    | medium-int8-b8 | 290 | 0.924 | 0.12 | meets all three, 10 ms of p95 headroom |
    | medium-int4 | 160 | 0.901 | 0.14 | meets all three, but dominated by distilled-small-int8 |
    | distilled-small-int8 | 75 | 0.902 | 0.06 | meets all three, accuracy 0.002 above the floor |
    | small-fp32 / small-int8 | 120 / 70 | 0.874 / 0.861 | 0.09 / 0.05 | fail accuracy |
    
    Three options are not beaten on every axis: medium-int8, medium-int8-b8 and
    distilled-small-int8.
    
    ## Decision
    
    Serve **medium-int8**: p95 230 ms, accuracy 0.924, $0.21 per 1,000 requests.
    
    ## Trade-offs accepted
    
    - **Accuracy:** 0.028 below today's large-fp32 (0.924 vs 0.952), about one more
      draft in 36 that needs rewriting.
    - **Cost:** $0.15/1k more than distilled-small-int8 and $0.09/1k more than
      medium-int8-b8. At ~430k requests a day that's about $39 a day over the batched
      variant. We pay it for headroom: 70 ms below the p95 target instead of 10 ms.
    - **Speed:** 155 ms slower at p95 than distilled-small-int8, which we accept for
      0.022 more accuracy and real margin over the 0.90 floor.
    
    ## Why not distilled-small-int8
    
    Fastest and cheapest, but 0.902 is 0.002 above the floor. One data shift or a
    newly added question category would put it under, and the benchmark set itself
    has more noise than that.
    
    ## Why not medium-int8-b8
    
    Same weights and accuracy, cheaper, but p95 290 ms leaves 10 ms of margin; batching
    latency grows with traffic spikes, which is when the budget matters most.
    
    ## Revisit if
    
    - p95 at peak exceeds 270 ms for a week (headroom gone; consider caching or a smaller model).
    - accuracy on the weekly labelled sample drops below 0.91.
    - traffic doubles past 860k requests a day, so the $0.09/1k batching saving exceeds about $77 a day.
    - a re-distilled small model reaches ≥ 0.92 accuracy.

### decision.json

    {
      "choice": "medium-int8",
      "expected_p95_ms": 230,
      "expected_accuracy": 0.924,
      "cost_per_1k_usd": 0.21,
      "revisit_if": [
        "p95 at peak above 270 ms for 7 days",
        "weekly labelled accuracy below 0.91",
        "traffic above 860k requests/day (batching would save > $77/day)",
        "a distilled small model reaching >= 0.92 accuracy"
      ]
    }

## Common mistakes

- **Picking the most accurate model.** large-fp32 is the best model and the
  worst product: the users who'd benefit from its accuracy have left before the
  answer arrives.
- **Optimising the average.** The router has the best-looking p50 (60 ms) and
  the second-best accuracy. But the 15% of requests it escalates take a second,
  so its p95 is 1,100 ms. Latency targets are tail targets because the tail is
  who leaves.
- **Ignoring cost until later.** medium-fp16 would be fine on accuracy, and
  "only" 120 ms over on latency, but it's also over budget. Each constraint is a
  constraint.
- **Choosing a dominated option** without noticing, like medium-int4.
- **Unmeasurable revisit triggers** ("if quality drops"). Nobody will ever notice
  that condition becoming true.

## Details worth knowing

- **The levers in the CSV are the real ones:** quantization (int8 is usually
  nearly free in accuracy, int4 costs more), distillation (a small model trained
  on the big one's answers), batching (cheaper per request, slower tail), and
  routing/cascades (cheap on average, slow tail unless escalation is rare and fast).
- **The benchmark is a model of reality.** Accuracy measured on a labelled set
  isn't "which errors matter to users". A 0.02 drop concentrated in billing
  questions is worse than one spread evenly. Look at error categories before
  trusting a single accuracy number.
- **What this doesn't cover:** caching frequent answers (often the biggest win
  for support traffic), measuring abandonment directly with an A/B test, and
  GPU vs CPU serving costs.
