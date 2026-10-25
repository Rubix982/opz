# Lab 44 · Solution (spoilers)

## What was wrong

| Group | Rule | Problem |
|---|---|---|
| jumpbox-sg | tcp 22 from `0.0.0.0/0` **and `::/0`** | SSH open to the whole internet, both IP families |
| web-sg | tcp 443 from `0.0.0.0/0` | web servers reachable around the load balancer, with its TLS policy, WAF and logs |
| web-sg | tcp 22 from `0.0.0.0/0` | SSH on every web server |
| db-sg | tcp 5432 from `10.0.0.0/16` | Postgres open to everything in the VPC, the jumpbox included |
| temp-debug-sg | all traffic from `0.0.0.0/0` | attached to nothing today, one mis-click from being attached tomorrow |

The old audit only matched a rule whose `FromPort` was exactly 22 with exactly
`0.0.0.0/0`. That missed the `::/0` half, the all-traffic rule (which has no
`FromPort`), the database and the unused group. Worse, it **revoked** the rules
it found and still exited 0. So the second run was "clean", CI stayed green, and
the fix was never in code: the next `network.py` deploy would put the rule back.
An audit that changes what it audits destroys its own evidence.

## The fix: a read-only audit

```python
import sys

from common import ec2, elbv2

ADMIN_PORTS = {22: "SSH", 3389: "RDP"}
DB_PORTS = {5432: "Postgres", 3306: "MySQL", 6379: "Redis", 27017: "MongoDB"}


def ports(rule: dict) -> str:
    if rule["IpProtocol"] == "-1":
        return "all traffic"
    lo, hi = rule["FromPort"], rule["ToPort"]
    return f"{rule['IpProtocol']} {lo}" if lo == hi else f"{rule['IpProtocol']} {lo}-{hi}"


def covers(rule: dict, port: int) -> bool:
    return rule["IpProtocol"] == "-1" or (rule["IpProtocol"] == "tcp" and rule["FromPort"] <= port <= rule["ToPort"])


def main() -> int:
    client = ec2()
    groups = client.describe_security_groups()["SecurityGroups"]

    # which groups are actually attached to something
    lb_groups = {g for lb in elbv2().describe_load_balancers()["LoadBalancers"] for g in lb.get("SecurityGroups", [])}
    used = set(lb_groups)
    for r in client.describe_instances()["Reservations"]:
        for i in r["Instances"]:
            used |= {g["GroupId"] for g in i["SecurityGroups"]}
    for eni in client.describe_network_interfaces()["NetworkInterfaces"]:
        used |= {g["GroupId"] for g in eni["Groups"]}

    findings = []
    for g in groups:
        gid, name = g["GroupId"], g["GroupName"]
        if name != "default" and gid not in used:
            findings.append((gid, name, "attached to nothing; delete it"))
        for rule in g["IpPermissions"]:
            world = [r["CidrIp"] for r in rule.get("IpRanges", []) if r["CidrIp"] == "0.0.0.0/0"]
            world += [r["CidrIpv6"] for r in rule.get("Ipv6Ranges", []) if r["CidrIpv6"] == "::/0"]
            public_https = gid in lb_groups and rule["IpProtocol"] == "tcp" and rule["FromPort"] == rule["ToPort"] == 443
            if world and not public_https:
                findings.append((gid, name, f"{ports(rule)} open to the world ({', '.join(world)})"))
            cidrs = [r["CidrIp"] for r in rule.get("IpRanges", []) if r["CidrIp"] != "0.0.0.0/0"]
            for port, what in DB_PORTS.items():
                if cidrs and covers(rule, port):
                    findings.append((gid, name, f"{what} ({port}) allowed by CIDR {', '.join(cidrs)}; "
                                                f"allow the app's security group instead"))

    for gid, name, what in findings:
        print(f"FINDING {gid} {name} {what}")
    print(f"{len(findings)} finding(s) in {len(groups)} security groups")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
```

Details that matter:
- `IpProtocol: "-1"` means all traffic and has no ports, so check it explicitly.
- Check `Ipv6Ranges` as well as `IpRanges`.
- The load balancer's 443 from the world is the one intended exposure; allow it
  by *which group it is on*, not by port alone.
- "Unused" must include load balancers. moto (and some real resources)
  attach groups without an instance, and a group used only by a load balancer is
  not unused.

## The fix: the network

```python
lb_sg = group("lb-sg", [{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": WORLD}])
# web only from the load balancer; no SSH (admins use SSM Session Manager)
web_sg = group("web-sg", [{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
                           "UserIdGroupPairs": [{"GroupId": lb_sg}]}])
# the database only from the web tier, by group, not by address range
db_sg = group("db-sg", [{"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
                         "UserIdGroupPairs": [{"GroupId": web_sg}]}])

instance("web-1", private, [web_sg])
instance("web-2", private, [web_sg])
instance("db-1", private, [db_sg])
```

The jumpbox and `temp-debug-sg` are gone. `check.sh` passes, and the audit is
clean.

**A security group reference** (`UserIdGroupPairs`) means "whatever is in that
group, wherever it is": a new web server is allowed on launch, and nothing else
in the subnet is. A CIDR means "any address in this range", including whatever
lands in that subnet next. Opening the database to the private subnet's CIDR
is the half-fix `check.sh` still fails.

**No jumpbox.** SSM Session Manager gives a shell through the SSM agent, which
connects *out* to AWS, so the instance needs **no inbound port at all**. You
need an instance role with `AmazonSSMManagedInstanceCore`, and either a route to
the SSM endpoints or VPC endpoints for them. Access is an IAM permission
(`ssm:StartSession`, which can be scoped by tag), and every session is logged to
CloudTrail and optionally to S3/CloudWatch. SSH-over-SSM still works for tools
that need SSH (`ProxyCommand aws ssm start-session …`).

## Details worth knowing

- **On real AWS:** AWS Config's `restricted-ssh` / `vpc-sg-open-only-to-authorized-ports`
  rules, Security Hub's foundational checks and IAM Access Analyzer do much of
  this audit continuously. Reachability Analyzer and Network Access Analyzer
  answer the "can A reach B" question for real, through routes and NACLs.
- **Egress matters too.** These groups still allow all outbound traffic. The
  database has no reason to start connections to the internet.
- **Fix the code, not the console.** The old audit's "quick fix" lived only in
  the account. Changes to security groups belong in `network.py` (or Terraform,
  CloudFormation), where a review sees them and the next deploy keeps them.
- **What this doesn't cover:** network ACLs and route tables (a second layer
  that can also leak), security groups on things other than instances and load
  balancers (Lambda in a VPC, RDS, EKS nodes), and detection: flow logs and
  GuardDuty tell you what *did* connect, not just what could.
