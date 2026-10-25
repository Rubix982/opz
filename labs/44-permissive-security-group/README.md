# Lab 44 · Security Group Too Permissive for Jumpbox

**Time:** ~45 min · **Needs:** Docker, Python 3 · **Cost:** free. Runs against a
local AWS emulator, not a real account.

## The incident

The jumpbox's auth log shows thousands of SSH login attempts an hour from all
over the world. Nobody got in (yet), but the review that followed found more:

- The web servers also take SSH, and HTTPS, straight from the internet,
  not just through the load balancer.
- The database accepts Postgres from *anything* in the VPC, the jumpbox included.
- A `temp-debug-sg` from last month's incident opens every port to the world.
  It's attached to nothing, which is exactly how it gets attached to something
  by mistake later.

And the security group audit that runs in CI has been green the whole time.

## About the emulator

The network lives in [moto](https://github.com/getmoto/moto), a local fake of
the AWS APIs, in a Docker container on `localhost:9044`. `infra/network.py` and
`app/audit.py` make ordinary `boto3` EC2 and ELBv2 calls, the same as against
real AWS. Only `endpoint_url` differs.

What's different from real AWS:
- moto stores security group rules but **moves no packets**, so nothing here
  can test a real connection. `tools/reach.py` is a small analyser over the
  ingress rules instead: "could A reach B on port P, and which rule allows it?"
  On AWS, **VPC Reachability Analyzer** does this properly, including route
  tables and network ACLs, which `reach.py` ignores. It also assumes egress is open.
- moto gives load balancers no IP address; `reach.py` pretends `10.0.0.10`.
- **SSM Session Manager** (how admins reach instances with no inbound ports at
  all) isn't emulated. It's explained in SOLUTION.md.
- Credentials are FAKE; moto accepts anything.

## Setup

```bash
./setup.sh                                  # emulator on :9044, .venv, builds infra/network.py
source .venv/bin/activate
python app/audit.py                         # the CI audit. Green. Run it twice, then look again.
python tools/reach.py internet jumpbox 22
python tools/reach.py internet web-1 22
python tools/reach.py jumpbox db-1 5432
python tools/reach.py web-1 db-1 5432
```

`infra/network.py` is the network as code: rerun `./setup.sh` after editing it.
`tools/incident.py` is a frozen copy of the network as it was. Leave it alone;
`check.sh` uses it to test your audit.

## Your job

1. **Map the exposure.** Who can reach what? Use `reach.py`, and read the rules themselves
   (`describe_security_groups()`). Then run the audit twice in
   a row and work out why the second run differs.
2. **Fix the audit** (`app/audit.py`). It should find every problem, change
   nothing, and fail CI when it finds something. Hints, one at a time:
   - "SSH from the world" isn't the only way to be open. What about a rule for
     *all* traffic (`IpProtocol: "-1"`, no ports at all)? A port range that
     includes 22? IPv6 (`::/0`)?
   - Not everything open to the world is wrong. What is the load balancer for?
   - Opening a database "to the VPC" by CIDR means everything in the VPC. What
     can a rule point at instead of an address range?
   - How do you tell a group is attached to nothing? Instances aren't the only
     things with security groups. Look at the load balancer.
   - Output contract for `check.sh`: one line per problem,
     `FINDING <group-id> <group-name> <what>`, then exit 1 if there were any.
3. **Fix the network** (`infra/network.py`) so the audit comes back clean and:
   internet → load balancer on 443; load balancer → web on 443; web → db on
   5432; nothing else. Hints:
   - Where a rule's source is "the things in that other group", use a security
     group reference, not a CIDR.
   - Admins still need a shell on the boxes. What gives them one with no inbound
     port at all? (You can't build it here; decide whether the jumpbox survives.)
4. **Prove it.** `./check.sh` runs your audit against the incident network,
   then builds *your* network from scratch and checks the paths.
5. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- What was open, and to whom:
- Why the old audit stayed green, and what it did that an audit must never do:
- Security group reference vs. CIDR, and why it matters for the database:
- How admins get a shell without port 22:
- What security groups alone don't cover:
