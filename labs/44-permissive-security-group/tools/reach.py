"""Can traffic get from A to B on a port? Answers from the security group rules.

    python tools/reach.py internet web-1 22
    python tools/reach.py web-lb web-1 443
    python tools/reach.py web-1 db-1 5432

A and B are instance Name tags, the load balancer's name, or "internet".
moto stores rules but moves no packets, so this is a small analyser over the
ingress rules only, like AWS's VPC Reachability Analyzer but much simpler: it
assumes egress is open and ignores route tables and network ACLs.
"""

import ipaddress
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from common import ec2 as ec2_client, elbv2 as elbv2_client  # noqa: E402

INTERNET_IP = "203.0.113.10"  # a documentation address standing in for "anyone"
LB_IP = "10.0.0.10"           # moto gives load balancers no address; pretend one in public-a


def endpoints() -> dict[str, dict]:
    """name -> {"ip": address, "groups": [security group ids]}"""
    ec2, elb = ec2_client(), elbv2_client()
    found: dict[str, dict] = {"internet": {"ip": INTERNET_IP, "groups": []}}
    for r in ec2.describe_instances()["Reservations"]:
        for i in r["Instances"]:
            if i["State"]["Name"] == "terminated":
                continue
            name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), i["InstanceId"])
            found[name] = {"ip": i["PrivateIpAddress"], "groups": [g["GroupId"] for g in i["SecurityGroups"]]}
    for lb in elb.describe_load_balancers()["LoadBalancers"]:
        found[lb["LoadBalancerName"]] = {"ip": LB_IP, "groups": lb.get("SecurityGroups", [])}
    return found


def reach(src: str, dst: str, port: int) -> tuple[bool, str]:
    """(allowed, why). why names the rule that allows it, e.g. "sg-ref sg-123 (web-sg)"."""
    ends = endpoints()
    if src not in ends or dst not in ends:
        return False, f"unknown endpoint ({src if src not in ends else dst})"
    s, d = ends[src], ends[dst]
    ec2 = ec2_client()
    names = {g["GroupId"]: g["GroupName"] for g in ec2.describe_security_groups()["SecurityGroups"]}
    groups = ec2.describe_security_groups(GroupIds=d["groups"])["SecurityGroups"] if d["groups"] else []
    for g in groups:
        for rule in g["IpPermissions"]:
            proto = rule["IpProtocol"]
            if proto not in ("-1", "tcp"):
                continue
            if proto == "tcp" and not (rule["FromPort"] <= port <= rule["ToPort"]):
                continue
            for pair in rule.get("UserIdGroupPairs", []):
                if pair["GroupId"] in s["groups"]:
                    return True, f"sg-ref {pair['GroupId']} ({names.get(pair['GroupId'])}) in {g['GroupName']}"
            for r in rule.get("IpRanges", []):
                if ipaddress.ip_address(s["ip"]) in ipaddress.ip_network(r["CidrIp"]):
                    return True, f"cidr {r['CidrIp']} in {g['GroupName']}"
            if src == "internet" and rule.get("Ipv6Ranges"):
                return True, f"cidr {rule['Ipv6Ranges'][0]['CidrIpv6']} in {g['GroupName']}"
    return False, "no rule allows it"


if __name__ == "__main__":
    src, dst, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    ok, why = reach(src, dst, port)
    print(f"{'ALLOWED' if ok else 'DENIED '}  {src} -> {dst}:{port}   {why}")
