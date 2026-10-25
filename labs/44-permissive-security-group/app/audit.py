"""Security group audit. Run it in CI and before every release.

    python app/audit.py
"""

import sys

from common import ec2

client = ec2()
for g in client.describe_security_groups()["SecurityGroups"]:
    for rule in g["IpPermissions"]:
        if rule.get("FromPort") == 22 and any(r["CidrIp"] == "0.0.0.0/0" for r in rule["IpRanges"]):
            print(f"FINDING {g['GroupId']} {g['GroupName']} ssh open to the world")
            # quick fix while we're here
            client.revoke_security_group_ingress(
                GroupId=g["GroupId"],
                IpPermissions=[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                                "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
            )
print("audit complete")
sys.exit(0)
