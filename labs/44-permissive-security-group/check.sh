#!/usr/bin/env bash
# Runs a fresh emulator on port 9144 and checks two things.
#   1. Your audit, against the network as it was during the incident
#      (tools/incident.py): it must report every problem (one FINDING line per
#      offending rule or group), exit nonzero, leave the load balancer's public
#      443 alone, and change nothing.
#   2. Your network (infra/network.py), built from scratch: the paths the shop
#      needs still work, by security group reference where they should; nothing
#      else is reachable; nothing but the load balancer's 443 is open to the
#      world; no unused groups; and your audit comes back clean.
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (makes .venv)"; exit 1; }
export AWS_ENDPOINT_URL=http://localhost:9144
fail=0

docker rm -f opz-lab44-check >/dev/null 2>&1
docker run -d --name opz-lab44-check -p 9144:5000 motoserver/moto:5.1.4 >/dev/null
trap 'docker rm -f opz-lab44-check >/dev/null 2>&1' EXIT
for _ in $(seq 1 40); do curl -s localhost:9144 >/dev/null && break; sleep 0.5; done
reset() { curl -s -X POST localhost:9144/moto-api/reset >/dev/null; }
snapshot() {
  $PY - <<'PY'
import json, sys
sys.path.insert(0, "app")
from common import ec2
gs = ec2().describe_security_groups()["SecurityGroups"]
print(json.dumps(sorted(gs, key=lambda g: g["GroupId"]), sort_keys=True, default=str))
PY
}

# --- 1. the audit, against the incident ------------------------------------------
reset
$PY tools/incident.py >.check.log 2>&1 || { echo "FAIL  tools/incident.py crashed; see .check.log"; exit 1; }
before=$(snapshot)
out=$($PY app/audit.py 2>>.check.log); rc=$?
echo "$out" >>.check.log
after=$(snapshot)

if [ "$rc" != 0 ]; then echo "pass  audit exits nonzero when it finds problems"
else echo "FAIL  audit exits 0 on the incident network (CI would stay green)"; fail=1; fi

findings() { echo "$out" | grep -c "^FINDING .* $1 " ; }
for want in "jumpbox-sg 1 SSH open to the world (IPv4 and IPv6)" \
            "web-sg 2 443 and 22 open to the world" \
            "db-sg 1 Postgres open to the whole VPC by CIDR" \
            "temp-debug-sg 1 everything open, attached to nothing"; do
  set -- $want; name=$1; n=$2; shift 2
  got=$(findings "$name")
  if [ "$got" -ge "$n" ]; then echo "pass  audit flags $name ($*)"
  else echo "FAIL  audit flags $name $got time(s), expected at least $n ($*)"; fail=1; fi
done
if [ "$(findings lb-sg)" = 0 ]; then echo "pass  audit leaves the load balancer's public 443 alone"
else echo "FAIL  audit flags lb-sg, whose 443 from the internet is the whole point"; fail=1; fi
if [ "$before" = "$after" ]; then echo "pass  audit changed nothing"
else echo "FAIL  audit modified security groups while auditing"; fail=1; fi

# --- 2. your network ---------------------------------------------------------------
reset
$PY infra/network.py >>.check.log 2>&1 || { echo "FAIL  infra/network.py crashed; see .check.log"; exit 1; }
$PY - <<'PY' || fail=1
import sys
sys.path.insert(0, "tools"); sys.path.insert(0, "app")
from common import ec2, elbv2
from reach import endpoints, reach

bad = 0
def expect(label: str, ok: bool) -> None:
    global bad
    print(("pass  " if ok else "FAIL  ") + label)
    bad += not ok

ends = endpoints()
missing = [n for n in ("web-lb", "web-1", "web-2", "db-1") if n not in ends]
expect("web-lb, web-1, web-2 and db-1 all exist" + (f" (missing {missing})" if missing else ""), not missing)
if missing:
    sys.exit(1)

ok, why = reach("internet", "web-lb", 443)
expect(f"internet -> web-lb:443 allowed", ok)
for w in ("web-1", "web-2"):
    ok, why = reach("web-lb", w, 443)
    expect(f"web-lb -> {w}:443 allowed by security group reference ({why})", ok and why.startswith("sg-ref"))
ok, why = reach("web-1", "db-1", 5432)
expect(f"web-1 -> db-1:5432 allowed by security group reference ({why})", ok and why.startswith("sg-ref"))

blocked = [("internet", "web-1", 443), ("internet", "web-1", 22), ("internet", "db-1", 5432),
           ("web-lb", "db-1", 5432), ("internet", "db-1", 22)]
if "jumpbox" in ends:
    blocked += [("internet", "jumpbox", 22), ("jumpbox", "db-1", 5432)]
leaks = [f"{s}->{d}:{p} ({reach(s, d, p)[1]})" for s, d, p in blocked if reach(s, d, p)[0]]
expect("nothing else gets through" + (f": {'; '.join(leaks)}" if leaks else
       " (internet to web/db/jumpbox, load balancer or jumpbox to db)"), not leaks)

client = ec2()
lb_groups = {g for lb in elbv2().describe_load_balancers()["LoadBalancers"] for g in lb.get("SecurityGroups", [])}
used = set(lb_groups)
for r in client.describe_instances()["Reservations"]:
    for i in r["Instances"]:
        used |= {g["GroupId"] for g in i["SecurityGroups"]}
open_world, unused = [], []
for g in client.describe_security_groups()["SecurityGroups"]:
    if g["GroupName"] != "default" and g["GroupId"] not in used:
        unused.append(g["GroupName"])
    for rule in g["IpPermissions"]:
        world = any(r["CidrIp"] == "0.0.0.0/0" for r in rule.get("IpRanges", [])) or \
                any(r["CidrIpv6"] == "::/0" for r in rule.get("Ipv6Ranges", []))
        lb_443 = g["GroupId"] in lb_groups and rule["IpProtocol"] == "tcp" and rule["FromPort"] == rule["ToPort"] == 443
        if world and not lb_443:
            open_world.append(f"{g['GroupName']} {rule['IpProtocol']} {rule.get('FromPort', 'all')}")
expect("only the load balancer's 443 is open to the world" + (f" (also: {', '.join(open_world)})" if open_world else ""),
       not open_world)
expect("no unused security groups" + (f" (unused: {', '.join(unused)})" if unused else ""), not unused)
sys.exit(1 if bad else 0)
PY

out=$($PY app/audit.py 2>>.check.log); rc=$?
echo "$out" >>.check.log
if [ "$rc" = 0 ] && ! echo "$out" | grep -q "^FINDING"; then echo "pass  audit is clean on your network"
else echo "FAIL  audit on your network: exit $rc, $(echo "$out" | grep -c '^FINDING') finding(s)"; fail=1; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
