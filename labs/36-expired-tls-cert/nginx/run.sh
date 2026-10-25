#!/bin/sh
# Runs nginx, and reloads it (gracefully: old workers finish their requests)
# whenever the certificate files change. Ops added this so a new cert can be
# dropped in without a restart. Nothing has ever dropped one in.
set -u
sum() { cat /etc/nginx/certs/tls.crt /etc/nginx/certs/tls.key 2>/dev/null | md5sum; }
nginx -g 'daemon off;' &
pid=$!
trap 'nginx -s quit; wait $pid; exit 0' TERM INT
last=$(sum)
while kill -0 $pid 2>/dev/null; do
  sleep 1
  now=$(sum)
  if [ "$now" != "$last" ]; then
    if nginx -t -q; then nginx -s reload && echo "cert changed: nginx reloaded"; fi
    last=$now
  fi
done
