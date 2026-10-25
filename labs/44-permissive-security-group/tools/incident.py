"""The network exactly as it was during the incident (a frozen copy of the
original infra/network.py). check.sh builds it to test that your audit finds
the problems. Do not edit it; fix infra/network.py instead.

The shop's network, as code: VPC, subnets, security groups, instances and the
load balancer. Running it against an empty account builds everything.

    internet ──443──▶ web-lb ──443──▶ web-1, web-2 ──5432──▶ db-1
    admins   ──22───▶ jumpbox ──22──▶ (everything)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from common import ec2 as ec2_client, elbv2 as elbv2_client  # noqa: E402

ec2, elb = ec2_client(), elbv2_client()
WORLD = [{"CidrIp": "0.0.0.0/0"}]


def tag(name: str) -> list[dict]:
    return [{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}]


def group(name: str, rules: list[dict]) -> str:
    gid = ec2.create_security_group(GroupName=name, Description=name, VpcId=vpc)["GroupId"]
    if rules:
        ec2.authorize_security_group_ingress(GroupId=gid, IpPermissions=rules)
    return gid


def instance(name: str, subnet: str, groups: list[str]) -> None:
    ec2.run_instances(ImageId="ami-12345678", InstanceType="t3.micro", MinCount=1, MaxCount=1,
                      SubnetId=subnet, SecurityGroupIds=groups, TagSpecifications=tag(name))


vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
public_a = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.0.0/24", AvailabilityZone="us-east-1a")["Subnet"]["SubnetId"]
public_b = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")["Subnet"]["SubnetId"]
private = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")["Subnet"]["SubnetId"]

lb_sg = group("lb-sg", [{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": WORLD}])
jump_sg = group("jumpbox-sg", [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": WORLD,
                                "Ipv6Ranges": [{"CidrIpv6": "::/0"}]}])
web_sg = group("web-sg", [
    # 443 from anywhere "so the health checks work"
    {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": WORLD},
    # SSH for debugging; the jumpbox was too slow
    {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": WORLD},
])
db_sg = group("db-sg", [{"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
                         "IpRanges": [{"CidrIp": "10.0.0.0/16"}]}])
# opened during last month's incident to rule the firewall out; "remove later"
group("temp-debug-sg", [{"IpProtocol": "-1", "IpRanges": WORLD}])

instance("jumpbox", public_a, [jump_sg])
instance("web-1", private, [web_sg])
instance("web-2", private, [web_sg])
instance("db-1", private, [db_sg])
elb.create_load_balancer(Name="web-lb", Subnets=[public_a, public_b], SecurityGroups=[lb_sg],
                         Scheme="internet-facing")
print(f"built {vpc}")
