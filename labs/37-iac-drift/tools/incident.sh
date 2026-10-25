#!/usr/bin/env bash
# Replays what was done by hand during last night's incident, the way someone
# clicking in the console would: straight to the cloud API, not through Terraform.
# Runs boto3 inside the emulator's container, so nothing is needed on your machine.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ${COMPOSE_PROJECT:+-p "$COMPOSE_PROJECT"} exec -T aws python - <<'PY'
import boto3
kw = dict(endpoint_url="http://127.0.0.1:5000", region_name="us-east-1",
          aws_access_key_id="testing", aws_secret_access_key="testing")
ec2, s3 = boto3.client("ec2", **kw), boto3.client("s3", **kw)
sg = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["web"]}])["SecurityGroups"][0]["GroupId"]

# 02:14 on-call (Priya): the new Prometheus couldn't scrape the web tier's
# metrics, so alerting was blind. Opened 9100 from the monitoring VPC.
try:
    ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[{
        "IpProtocol": "tcp", "FromPort": 9100, "ToPort": 9100,
        "IpRanges": [{"CidrIp": "10.42.0.0/16", "Description": "INC-4471 prometheus scrape"}]}])
except ec2.exceptions.ClientError as e:
    if "Duplicate" not in str(e):  # already there (e.g. it's in code now)
        raise

# 02:40 someone else, "tidying up" while they were in there.
ec2.create_tags(Resources=[sg], Tags=[{"Key": "env", "Value": "production"},
                                     {"Key": "edited-by", "Value": "jsmith"}])

# 03:05 the reports bucket was "using too much space": versioning switched off.
s3.put_bucket_versioning(Bucket="opz-lab37-reports", VersioningConfiguration={"Status": "Suspended"})
print("replayed 3 hand changes from INC-4471")
PY
