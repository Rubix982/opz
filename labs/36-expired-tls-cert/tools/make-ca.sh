#!/bin/sh
# Creates the lab's private CA in <dir>/ca: a FAKE, lab-only certificate authority.
# Usage: make-ca.sh <pki-dir>
set -eu
dir=${1:-/pki}
mkdir -p "$dir/ca"
[ -f "$dir/ca/ca.crt" ] && { echo "CA already exists in $dir/ca"; exit 0; }
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
  -subj "/CN=opz lab36 FAKE local CA/O=opz labs (FAKE, lab only)" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash" \
  -keyout "$dir/ca/ca.key" -out "$dir/ca/ca.crt" 2>/dev/null
echo "CA created: $dir/ca/ca.crt"
