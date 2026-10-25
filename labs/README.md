# opz labs

Bite-sized, standalone versions of the scenarios in [`CHECKLIST.md`](CHECKLIST.md).
Each lab is one folder: break → diagnose → fix → prove → retro. Nothing here
depends on any other project, and nothing costs money.

Every lab has the same parts:
- `README.md` — the incident, your job, hints, a 5-line retro to fill in
- `app/` (or a skeleton to fill in) — the smallest stack that reproduces the problem
- `check.sh` — passes only when the problem is truly fixed
- `SOLUTION.md` — spoilers, read last

Three kinds:
- **Tracks A and C (most):** a broken system. Find the cause, fix it, prove it.
- **Track B (labs 20–24, 38–39) and C1 batching (41):** nothing is broken yet. Build the thing from a skeleton,
  and `check.sh` injects the failure: races, crashes, pauses, overload.
- **Track D (labs 30–34, 43–44):** cloud scenarios run against local emulators (MinIO for
  S3, moto for SQS/SSM/EC2/Secrets Manager). Same API calls as real AWS, no
  account. Each README says what the emulator can't prove.

**Status:** `solved` = fixed, proven, retro written · `ready` = built and waiting.
Lines on the checklist with no lab yet show as "not built yet" on the site.

| # | Lab | Needs | Status |
|---|-----|-------|--------|
| 01 | [Hardcoded Credentials in Dockerfile](01-hardcoded-creds-dockerfile/) | Docker | solved |
| 02 | [Secret Exposed Through Environment Variables](02-env-var-secret-exposure/) | Docker Compose | solved |
| 03 | [Secret Committed to a Repo](03-secret-committed-to-repo/) | git, gitleaks, git-filter-repo | solved |
| 04 | [Debugging a CrashLoopBackOff Pod](04-crashloopbackoff/) | Docker, kind, kubectl | solved |
| 05 | [Resource Starvation due to Misconfigured Requests & Limits](05-oomkilled/) | Docker, kind, kubectl | ready |
| 06 | [Replay Attack via Insecure Webhooks](06-webhook-replay/) | Python | ready |
| 07 | [Graceful Shutdown (PID 1 ignores SIGTERM)](07-graceful-shutdown/) | Docker | ready |
| 08 | [JWT Replay Due to No Expiry Validation](08-jwt-validation/) | Python | ready |
| 09 | [Unsecured Redis Allows Remote Access](09-unsecured-redis/) | Docker Compose | ready |
| 10 | [Credential Rotations Not Propagated](10-credential-rotation/) | Docker Compose, Python | ready |
| 11 | [Escalating Build Times Due to Dependency Bloat](11-image-bloat/) | Docker | ready |
| 12 | [Pod Crash on Timezone Mismatch](12-timezone-mismatch/) | Docker | ready |
| 13 | [Forgotten Default Credentials](13-default-credentials/) | Docker Compose | ready |
| 14 | [Post-Deployment Failure Due to Missing Migration](14-missing-migration/) | Docker Compose, Postgres | ready |
| 15 | [Rate Limiting Not Enforced on Public API](15-rate-limiting/) | Docker Compose, NGINX | ready |
| 16 | [DoS Attack via Large JSON Body](16-large-json-dos/) | Docker Compose, NGINX | ready |
| 17 | [Log Injection Attack on Centralized Logging](17-log-injection/) | Python | ready |
| 18 | [Silent Data Loss from Wrong Volume Mount](18-volume-data-loss/) | Docker, kind, kubectl | ready |
| 19 | [Alert Not Fired Due to Misconfigured Label](19-alert-label/) | Docker Compose, Prometheus | ready |
| 20 | [Producer-Consumer with Bounded Buffer](20-producer-consumer/) | Python (build) | ready |
| 21 | [Circuit Breaker Implementation](21-circuit-breaker/) | Python (build) | ready |
| 22 | [Cache with Expiration & Eviction](22-ttl-lru-cache/) | Python (build) | ready |
| 23 | [Leader Election in a Cluster](23-leader-election/) | Python (build) | ready |
| 24 | [Build a Job Queue from Scratch](24-job-queue/) | Python, SQLite (build) | ready |
| 25 | [Improper Rollback](25-improper-rollback/) | Python | ready |
| 26 | [Environment Drift](26-environment-drift/) | Docker, Python | ready |
| 27 | [Model Theft via API](27-model-theft/) | Python, scikit-learn | ready |
| 28 | [Silent Job Failures](28-silent-job-failures/) | Python | ready |
| 29 | [Protecting AI Model Artifacts](29-model-artifact-storage/) | Docker Compose, MinIO | ready |
| 30 | [S3 Bucket Data Leak Simulation](30-s3-bucket-leak/) | Docker Compose, MinIO (local S3) | ready |
| 31 | [Parameter Store Used Insecurely in Plain Text](31-parameter-store-plaintext/) | Docker Compose, moto (local AWS) | ready |
| 32 | [SQS Message Flood Unprocessed, Causes Latency](32-sqs-poison-message/) | Docker, moto (local AWS) | ready |
| 33 | [Zombie Resources Driving Up Cloud Bill](33-zombie-resources/) | Docker, moto (local AWS) | ready |
| 34 | [Secrets Manager Rotation Fails Silently](34-secrets-rotation/) | Docker, moto (local AWS) | ready |
| 35 | [Overprivileged Service Accounts in K8s](35-overprivileged-sa/) | Docker, kind, kubectl | ready |
| 36 | [Expired TLS Cert Brings Down Frontend](36-expired-tls-cert/) | Docker Compose, openssl | ready |
| 37 | [Drift in IaC Deployments](37-iac-drift/) | Docker, Terraform (in a container), moto | ready |
| 38 | [Build a Mini HTTP Server](38-mini-http-server/) | Python, sockets (build) | ready |
| 39 | [Network Partition Simulation](39-network-partition/) | Python (build) | ready |
| 40 | [Transaction Isolation Levels Simulation](40-isolation-levels/) | Docker Compose, Postgres | ready |
| 41 | [Batching](41-dynamic-batching/) | Python (build) | ready |
| 42 | [Model Speed vs Accuracy](42-speed-vs-accuracy/) | Python (design) | ready |
| 43 | [API Gateway Key Rotation Breaks Clients](43-api-key-rotation/) | Docker, moto (local AWS) | ready |
| 44 | [Security Group Too Permissive for Jumpbox](44-permissive-security-group/) | Docker, moto (local AWS) | ready |
