# Lab 26 · Solution (spoilers)

## What drifted

`requirements.txt` said `featurekit>=1.4`. That's a range, so pip installs the
newest release available *at build time*:

| Build | featurekit | tinymath (indirect) | Result |
|---|---|---|---|
| Laptop (Sept) | 1.4.0 | 1.0.0 | the paper's numbers |
| Image (today) | 2.0.0 | 1.1.0 | `ImportError`: `standardize` was renamed `scale` in 2.0 |
| `featurekit==1.4.0` only | 1.4.0 | 1.1.0 | runs, but **different numbers**: tinymath 1.1 changed its default rounding from 2 to 3 digits |

The second drift is the dangerous one. A crash gets noticed; slightly different
model weights get published.

## The fix

**1. Lock everything, with hashes.** `app/requirements.lock`, from the laptop's
`pip freeze` plus `pip hash` on each wheel:

```
featurekit==1.4.0 \
    --hash=sha256:7a8d04e87fdb67d226da1a3ad922b8599227d8244ffd7a21a0d469c1378123cd
tinymath==1.0.0 \
    --hash=sha256:b7147cb7f7334b1d106285d2ec23c5fcb60b40916332f7758fe34d1e2e0875c2
```

In a real project, generate it rather than writing it by hand:
`uv pip compile requirements.in --generate-hashes -o requirements.lock` (or
`pip-compile --generate-hashes`). Keep `requirements.in` for what you *want*
(`featurekit>=1.4`), and the lock for what you *get*. Re-lock deliberately,
review the diff, and rerun the experiments.

**2. Install only from the lock, verifying hashes.** With `--require-hashes`,
pip refuses any file whose hash isn't listed, and also refuses any package that
isn't in the lock at all, so an unpinned indirect dependency becomes an error
instead of a surprise.

**3. Pin the base image by digest.** Tags move; digests don't.

```dockerfile
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ARG INDEX=index/2026-10-25
COPY ${INDEX}/ /wheels/

WORKDIR /app
COPY app/requirements.lock .
RUN pip install --no-cache-dir --no-index --find-links /wheels --require-hashes -r requirements.lock
...
```

(Use the digest your own machine shows. That one is what this lab was verified with.)

**4. Use the same lock on the laptop.** `pip install --require-hashes -r app/requirements.lock`
in the venv too. Better still, develop inside the same image (a devcontainer),
so "dev and prod" really are one environment.

`check.sh`:

```
pass  build from the 2026-10-25 index reproduces the paper's numbers
pass  build from the 2026-11-01 index reproduces the paper's numbers
pass  same packages a week apart: featurekit==1.4.0 tinymath==1.0.0
pass  build refuses tampered packages (DO NOT MATCH THE HASHES)
pass  base image pinned by digest
LAB PASSED
```

## Details worth knowing

- **Hashes are a supply-chain control, not just a reproducibility one.** A
  compromised mirror, a hijacked maintainer account or a re-uploaded file all
  produce the same version number with different contents. With hashes, the
  install fails; without them, it runs the attacker's code at build time.
- **Pinning has a cost: you stop getting fixes.** Pair the lock with automated
  update PRs (Dependabot, Renovate) that bump versions, re-run the tests and the
  reproduction check, and let a human merge.
- **Digest pinning has the same cost** for OS security patches. Rebuild on a
  schedule from a bumped digest, rather than whenever the tag happens to move.
- **What a lockfile doesn't pin:** OS packages from `apt-get` (pin versions or
  use a snapshot mirror), the Python interpreter itself (the digest does), CPU
  features and BLAS libraries (numerical results can differ across hardware even
  with identical packages), and random seeds. Exact reproducibility of ML results
  needs all of these.
