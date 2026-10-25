#!/usr/bin/env bash
cd "$(dirname "$0")" && docker compose down -v
rm -rf .check-work infra/terraform.tfstate infra/terraform.tfstate.backup
