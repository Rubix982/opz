# Lab 37 · Solution (spoilers)

## What the queued apply would have done

```
~ aws_s3_bucket_versioning.reports   status = "Suspended" -> "Enabled"
~ aws_security_group.web             ingress: - 9100 from 10.42.0.0/16   ← the emergency fix
                                     tags:    env "production" -> "prod", - edited-by
```

Terraform makes reality match the **code**. A rule that exists only in the cloud
is drift, and drift gets undone. Applying would have closed 9100 and blinded
alerting again, the exact outage from last night, caused by a "routine" change.

## Reconcile

**Keep → codify.** Add the rule to `infra/main.tf`:

```hcl
  # Codified from INC-4471: Prometheus in the monitoring VPC scrapes node metrics.
  ingress {
    description = "INC-4471 prometheus scrape"
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    cidr_blocks = ["10.42.0.0/16"]
  }
```

**Revert → apply.** `tools/tf.sh apply`: versioning goes back to Enabled, the
tags go back to the standard, and the 9100 rule stays because it's in code now.
`tools/tf.sh plan -detailed-exitcode` then exits 0.

## The drift check

The old script ran `plan` and exited 0, because `plan` succeeds whether or not
it finds changes. It reported "no failure", not "no drift".

```bash
tools/tf.sh plan -detailed-exitcode -no-color -lock=false
rc=$?   # 0 = matches, 2 = differs, 1 = error
...
exit $rc
```

- `-lock=false`: a read-only check shouldn't block a real apply.
- Exit 2 should page or open a ticket; exit 1 should alert too. A broken drift
  check that's silently "green" is how this incident started.

## Why not `-refresh-only`?

`plan -refresh-only` compares real resources with the **state**, not the code,
so in principle it shows only drift. But it also reports harmless changes to
*computed* attributes. Here, right after a fresh apply, it flags
`aws_s3_bucket.reports.versioning` (`enabled false -> true`), because the
bucket's own attribute was recorded before the separate versioning resource
was applied. Same on real AWS. A check that pages on a clean environment gets
ignored within a week. A normal `plan -detailed-exitcode` only reports
differences that would cause changes. It also catches code merged but never
applied, which you want to know about too.

## Details worth knowing

- **State is Terraform's memory, not the truth.** Keep it in a remote backend
  with locking (S3 + DynamoDB, Terraform Cloud), never in git: it holds IDs and
  often secrets. Here it's local, next to a throwaway emulator.
- **`lifecycle { ignore_changes = [...] }`** is for attributes something else is
  *supposed* to manage (an autoscaler's desired count). It's not a way to make
  drift go away.
- **Codifying needs the code to match exactly**, description included, or the
  next plan wants to replace the rule.
- **Prevention beats detection:** read-only console roles, break-glass access
  that's logged and time-boxed, and "every emergency change gets a PR within a
  day" as part of closing the incident.
- **What this doesn't cover:** drift in resources Terraform doesn't manage at
  all. A security group created by hand never appears in any plan. That needs
  an inventory (AWS Config, `terraformer`/import scans) compared with state.
