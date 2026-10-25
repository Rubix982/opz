#!/usr/bin/env bash
# Builds the tools image, creates the lab CA (once), installs the certificate
# that was put on the server by hand a year ago, and starts the frontend on
# https://localhost:8436. Re-run to reset the certificate to that state.
set -euo pipefail
cd "$(dirname "$0")"
docker build -q -t opz-lab36-tools tools >/dev/null
mkdir -p pki/live
tool() { docker run --rm -v "$PWD/pki:/pki" opz-lab36-tools "$@"; }
tool make-ca.sh /pki
tool issue.sh /pki expired
docker compose up -d --force-recreate --remove-orphans
echo "Up. Try: curl --cacert pki/ca/ca.crt https://localhost:8436/   and: ./monitor.sh"
