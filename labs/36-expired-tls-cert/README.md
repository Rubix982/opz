# Lab 36 · Expired TLS Cert Brings Down Frontend

**Time:** ~45 min · **Needs:** Docker Compose · **Cost:** free, all local

## The incident

Saturday morning: browsers show a full-page "Your connection is not private"
warning, and every API client fails with `certificate has expired`. The
frontend's certificate was installed by hand a year ago, with a calendar reminder
to renew it that nobody kept.

The on-call dashboard is green. The health check (`monitor.sh`) says
`OK https://localhost:8436 answered 200`, every minute, all night.

## Setup

```bash
./setup.sh                                              # local CA + last year's certificate + the frontend
curl --cacert pki/ca/ca.crt https://localhost:8436/     # a client that trusts our CA: fails
./monitor.sh                                            # the health check: "OK"
```

Everything runs locally:
- **A private certificate authority**, made by `setup.sh` in `pki/ca/`. It is FAKE
  and lab-only; your browser and OS don't trust it, and that's the point. Clients
  in this lab trust exactly this CA.
- **`tools/issue.sh`**, the manual way the certificate was made last year:
  `docker run --rm -v "$PWD/pki:/pki" opz-lab36-tools issue.sh /pki 90d`
  (validity like `90d`, `120s` or `expired`). It writes `pki/live/tls.crt` and `tls.key`.
- **The frontend**, nginx with a small watcher (`nginx/run.sh`) that reloads
  gracefully whenever the certificate files change.

> **Kubernetes note:** in a cluster you wouldn't build this yourself. cert-manager
> does it: a `Certificate` resource names the DNS names and an `Issuer` (Let's
> Encrypt, or a CA like this one), and cert-manager renews it into a Secret
> before it expires (by default when a third of its lifetime is left); the
> ingress controller picks up the new Secret without a restart. This lab builds
> the same loop by hand so you can see each piece.

## Your job

1. **Diagnose.** Why is the monitor green while every real client fails? Hints, one at a time:
   - Read `monitor.sh`. What does `curl -k` turn off?
   - `openssl s_client -connect localhost:8436 </dev/null 2>/dev/null | openssl x509 -noout -dates -issuer -subject`
   - Uptime ("did it answer?") and correctness ("would a real client accept it?")
     are different questions. Which one did the monitor ask?
2. **Fix the monitor.** It should page (exit nonzero) when the served
   certificate is expired, doesn't chain to the CA, or has fewer than
   `WARN_DAYS` (default 14) left, and be quiet otherwise. It must accept a
   `CA_FILE` environment variable (default `pki/ca/ca.crt`) for the CA to trust.
   - `openssl x509 -checkend <seconds>` answers "will this expire within N seconds?"
   - `openssl verify -CAfile …` checks the chain.
3. **Make renewal automatic.** A calendar reminder is the bug. Add something that
   starts with `docker compose up` and, about every 10–30 seconds, replaces any
   certificate with fewer than 30 days left with a fresh one from the lab CA.
   - The `opz-lab36-tools` image already has `openssl` and `issue.sh`.
   - You don't need to restart or signal nginx: the watcher reloads it when the files change.
   - Don't set `container_name:` on new services (check.sh runs a second copy alongside yours).
4. **Prove it.** `./check.sh` starts its own copy with a fresh CA and last year's
   certificate, tests the monitor against expired, nearly-expired and healthy
   certificates, waits for your renewer to fix the expired one, then drops in a
   2-minute certificate **while requests are flowing** and checks it's renewed
   with no failed requests.
5. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why the health check stayed green:
- What a certificate's validity window is, and how to read it with openssl:
- Monitor uptime vs. monitor expiry, and what each one catches:
- How the renewal works, and why it renews at 30 days, not at expiry:
- Why the reload didn't drop requests, and what would have:
