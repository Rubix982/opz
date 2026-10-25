#!/usr/bin/env bash
cd "$(dirname "$0")" && docker compose down -v --remove-orphans --rmi local && rm -f .env.app
