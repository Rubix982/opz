# Lab 37 · Drift in IaC Deployments

**Time:** ~45 min · **Needs:** Docker · **Cost:** free, all local

Runs against a **local AWS emulator** (moto) with Terraform from a pinned Docker
image: no AWS account, nothing installed on your machine. The Terraform code,
the plan output and the drift workflow are exactly what you'd use on real AWS;
only the endpoint differs (see `infra/provider.tf`).

## The incident

INC-4471, last night. Alerting was blind because the new Prometheus couldn't
scrape the web tier, so the on-call engineer opened port 9100 from the
monitoring VPC (10.42.0.0/16) **by hand**. That fixed it. While they were in the
console, someone else "tidied up" the security group's tags and switched off
versioning on the reports bucket to save space.

This morning a routine `terraform apply` is queued for an unrelated change. The
nightly drift check has been green all along.

The incident review decided:
- **Keep** the 9100 rule from the monitoring VPC. It's needed.
- **Revert** everything else that was done by hand.

## Setup

```bash
./setup.sh                    # emulator on localhost:9037, applies infra/, replays the night's hand changes
tools/tf.sh plan              # Terraform, from a pinned image, on the lab's network
tools/drift-check.sh; echo "exit=$?"
```

`tools/tf.sh` passes its arguments to `terraform` (1.9.8, AWS provider pinned
by `infra/.terraform.lock.hcl`). Re-run `./setup.sh` to start over.

## Your job

1. **Read the plan before applying anything.** What would the queued
   `terraform apply` do to each hand change? Hints, one at a time if you're stuck:
   - `tools/tf.sh plan`: look for `-` lines inside `aws_security_group.web`.
   - Terraform's state says what it *last* applied. `plan` refreshes the state
     from the real resources and compares both with the code. Anything changed
     by hand shows up as a change Terraform wants to *undo*.
   - Why has `tools/drift-check.sh` been green every night? Read it, and look up
     `terraform plan -detailed-exitcode`.
2. **Reconcile, one change at a time:**
   - Bring the change you're keeping **into the code**, so applying puts it back
     rather than removing it.
   - **Revert** the others by applying the code.
3. **Fix the drift check** so it exits non-zero when live infrastructure differs
   from the code, and zero when it doesn't. You'll probably meet
   `-refresh-only` too. Try it on a freshly applied environment and see what it says.
4. **Prove it.** `./check.sh` applies your code to a fresh emulator, makes a new
   hand change, runs your drift check, then checks your own environment is reconciled.
5. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- What drift is, and how `plan` finds it:
- What the queued apply would have done to last night's fix:
- Codify or revert: how I decided for each change:
- Why the drift check was always green, and what exit codes mean now:
- `plan` vs `plan -refresh-only` for a scheduled check:
- What stops people changing things by hand in the first place:
