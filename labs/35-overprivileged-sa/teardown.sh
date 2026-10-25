#!/usr/bin/env bash
kind delete cluster --name opz-lab35
docker rmi opz-lab35-app:1.0 >/dev/null 2>&1 || true
