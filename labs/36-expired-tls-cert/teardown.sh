#!/usr/bin/env bash
cd "$(dirname "$0")"
docker compose down -v --remove-orphans
docker rmi opz-lab36-tools >/dev/null 2>&1 || true
rm -rf pki .check-ctx
