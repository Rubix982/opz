#!/usr/bin/env bash
# The frontend's health check. Runs every minute from cron; exit 0 = healthy,
# anything else pages the on-call. Usage: ./monitor.sh [host:port]
target=${1:-localhost:8436}
code=$(curl -sk -o /dev/null -w '%{http_code}' "https://$target/")
if [ "$code" = 200 ]; then
  echo "OK  https://$target answered 200"
  exit 0
fi
echo "DOWN  https://$target answered ${code:-nothing}"
exit 1
