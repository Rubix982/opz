#!/bin/sh
# Issues a server certificate for "localhost" and "frontend" from the lab CA and
# installs it in <pki-dir>/live as tls.crt + tls.key (replacing both at once).
#
# Usage: issue.sh <pki-dir> <validity>
#   validity:  90d      valid from now for 90 days
#              120s     valid from now for 120 seconds (for testing renewals)
#              expired  valid for a day, a year ago (what we have in production)
set -eu
dir=$1
validity=$2
now=$(date +%s)
case "$validity" in
  expired) start=$((now - 366 * 86400)); end=$((now - 365 * 86400)) ;;
  *d) start=$((now - 60)); end=$((now + ${validity%d} * 86400)) ;;
  *s) start=$((now - 60)); end=$((now + ${validity%s})) ;;
  *) echo "validity must be like 90d, 120s or expired" >&2; exit 2 ;;
esac
fmt() { date -u -d "@$1" +%Y%m%d%H%M%SZ; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/db" "$dir/live"
: > "$work/db/index.txt"
openssl rand -hex 16 > "$work/db/serial"
cat > "$work/ca.cnf" <<CNF
[ ca ]
default_ca = lab
[ lab ]
database = $work/db/index.txt
new_certs_dir = $work/db
serial = $work/db/serial
certificate = $dir/ca/ca.crt
private_key = $dir/ca/ca.key
default_md = sha256
policy = anything
x509_extensions = leaf
unique_subject = no
[ anything ]
commonName = supplied
[ leaf ]
subjectAltName = DNS:localhost,DNS:frontend,IP:127.0.0.1
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
[ req ]
distinguished_name = dn
prompt = no
[ dn ]
CN = localhost
CNF
openssl req -new -newkey rsa:2048 -nodes -keyout "$work/tls.key" -out "$work/tls.csr" \
  -config "$work/ca.cnf" 2>/dev/null
openssl ca -batch -config "$work/ca.cnf" -in "$work/tls.csr" -out "$work/tls.crt" -notext \
  -startdate "$(fmt $start)" -enddate "$(fmt $end)" 2>"$work/err" || { cat "$work/err" >&2; exit 1; }

# Replace the pair as atomically as two files allow: new names first, then rename.
cp "$work/tls.key" "$dir/live/.tls.key.new"
cp "$work/tls.crt" "$dir/live/.tls.crt.new"
chmod 644 "$dir/live/.tls.key.new" "$dir/live/.tls.crt.new"
mv "$dir/live/.tls.key.new" "$dir/live/tls.key"
mv "$dir/live/.tls.crt.new" "$dir/live/tls.crt"
echo "issued: $(openssl x509 -in "$dir/live/tls.crt" -noout -enddate)"
