# Lab 36 · Solution (spoilers)

## Why everything was green

`monitor.sh` ran `curl -k`. `-k` (`--insecure`) skips certificate verification
entirely: expired, wrong name and untrusted issuer all count as fine, so the
check only asked "does something answer on port 8436?". Real clients ask
"would I trust this?", and the answer had been no since the certificate's
`notAfter` date passed.

```bash
openssl s_client -connect localhost:8436 </dev/null 2>/dev/null | openssl x509 -noout -dates
# notBefore=…  notAfter=<a year ago>
```

## The monitor

```bash
#!/usr/bin/env bash
target=${1:-localhost:8436}
host=${target%:*}
warn_days=${WARN_DAYS:-14}
ca=${CA_FILE:-$(dirname "$0")/pki/ca/ca.crt}

pem=$(mktemp); trap 'rm -f "$pem"' EXIT
if ! openssl s_client -connect "$target" -servername "$host" </dev/null 2>/dev/null | openssl x509 >"$pem" 2>/dev/null; then
  echo "CRIT  $target: no certificate (down?)"; exit 2
fi
end=$(openssl x509 -in "$pem" -noout -enddate | cut -d= -f2)
if ! openssl x509 -in "$pem" -noout -checkend 0 >/dev/null; then
  echo "CRIT  $target: certificate EXPIRED on $end"; exit 2
fi
if ! openssl verify -CAfile "$ca" "$pem" >/dev/null 2>&1; then
  echo "CRIT  $target: certificate doesn't chain to $ca"; exit 2
fi
if ! openssl x509 -in "$pem" -noout -checkend $((warn_days * 86400)) >/dev/null; then
  echo "WARN  $target: certificate expires $end (under $warn_days days)"; exit 1
fi
echo "OK    $target: certificate valid until $end"
```

It reads the certificate actually being **served**, not the file on disk, so it
also catches "renewed the file but never reloaded".

## Automatic renewal

`renew.sh`:

```sh
#!/bin/sh
set -u
before=$(( ${RENEW_BEFORE_DAYS:-30} * 86400 ))
while true; do
  crt=/pki/live/tls.crt
  if [ ! -f "$crt" ] || ! openssl x509 -in "$crt" -noout -checkend "$before" >/dev/null 2>&1; then
    echo "renewing: $( [ -f "$crt" ] && openssl x509 -in "$crt" -noout -enddate || echo 'no certificate')"
    issue.sh /pki "${VALIDITY:-90d}" || echo "renewal FAILED; will retry"
  fi
  sleep "${INTERVAL_SECONDS:-10}"
done
```

and a service in `compose.yaml`:

```yaml
  renewer:
    build: tools
    image: opz-lab36-tools
    command: ["/bin/sh", "/renew.sh"]
    environment:
      RENEW_BEFORE_DAYS: "30"
      INTERVAL_SECONDS: "10"
    volumes:
      - ./renew.sh:/renew.sh:ro
      - ./pki:/pki
```

`issue.sh` writes the new key and certificate under temporary names and renames
them into place, so nginx never reads half a file. The watcher sees the change,
runs `nginx -t`, then `nginx -s reload`. A reload starts new workers with the new
certificate while old workers finish the requests they're serving, so nothing is
dropped. A *restart* would drop them.

## The tempting half-fix

A renewer that makes its own **self-signed** certificate (`openssl req -x509 …`)
renews on time, and `curl -k` is happy, but no client trusts it. That's the same
outage under a new date. `check.sh` fails it on "doesn't chain to the CA".

## Details worth knowing

- **Renew early.** 90-day certificates renewed at 30 days left give two months of
  retries if the CA or DNS is down. Let's Encrypt is moving to much shorter
  lifetimes, which only works with automation like this.
- **Monitor expiry, not just uptime,** and monitor from outside, against what's
  served. Blackbox exporter's `probe_ssl_earliest_cert_expiry` is the usual
  Prometheus metric, alerting at about 14 days.
- **Python 3.13+ checks certificates strictly.** While building this lab, the first
  CA lacked `keyUsage` and `basicConstraints=critical`; `curl` accepted it,
  Python refused it ("CA cert does not include key usage extension"). Real CAs
  set these. Hand-rolled ones often don't.
- **What this doesn't cover:** the CA itself expiring (here, in 10 years: the
  next forgotten reminder), revocation if a key leaks, certificates pinned inside
  mobile apps, and every *other* certificate (internal services, client certs,
  the database). An inventory of what you serve matters as much as renewing one of them.
