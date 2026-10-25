# Lab 25 · Solution (spoilers)

## What went wrong

`deploy.sh` copied the new version **over** the live one, file by file, chunk by
chunk. During the copy, `models/current/` is in one of two bad states:

- **A half-written file** (`weights.json` cut off in the middle). The service's
  reload fails to parse it, and the request gets a 500.
- **Two complete files from different versions** (v1 weights, v2 preprocessing).
  Both parse fine, so the service happily computes a score from a model that never
  existed. That's a 200 with a wrong answer, the worst kind of failure, because
  nothing alerts on it.

And `predict 200` in the logs can't tell you which version produced an answer,
so afterwards nobody can say which requests were affected.

## The fix

**1. Live is a pointer, not a copy.** `models/current` becomes a symlink to one
complete, never-edited version directory. Deploying or rolling back means
building the new link beside it and **renaming** it over the old one. rename(2)
is atomic: any reader sees the old target or the new one, never something in between.

```bash
#!/usr/bin/env bash
# Make a model version live: ./deploy.sh v1   (also how we roll back)
# models/current is a symlink to one complete, never-edited version directory.
# Switching is one atomic rename, so a reader sees the old version or the new one,
# never half of each.
set -euo pipefail
cd "$(dirname "$0")"
[ -d "models/$1" ] || { echo "no such version: models/$1"; exit 1; }
# One-time migration: the old layout had a real directory here.
[ -L models/current ] || rm -rf models/current
python3 - "$1" <<'PY'
import os, sys
os.symlink(sys.argv[1], "models/current.tmp")      # relative: models/current -> v1
os.replace("models/current.tmp", "models/current")  # rename(2): atomic
PY
echo "live: $(readlink models/current)"
```

**2. The service resolves the pointer once per change and loads that whole
directory**, refusing a directory whose files disagree. Each request holds one
model reference from start to finish, and logs its version:

```python
_lock = threading.Lock()
_loaded: tuple[str, dict] | None = None  # (resolved version directory, model)


def model() -> dict:
    """The live model. Resolve the symlink once, then load that whole directory.

    Version directories are complete and never edited, so whatever directory we
    resolve to is consistent. The swap to a new one is a single assignment.
    """
    global _loaded
    target = os.path.realpath(MODEL_DIR)
    current = _loaded
    if current is not None and current[0] == target:
        return current[1]
    with _lock:
        if _loaded is None or _loaded[0] != target:
            d = Path(target)
            pre = json.loads((d / "preprocess.json").read_text())
            wts = json.loads((d / "weights.json").read_text())
            if pre["version"] != wts["version"]:
                raise RuntimeError(f"{d} mixes {pre['version']} and {wts['version']}")
            _loaded = (target, {"pre": pre, "wts": wts, "version": pre["version"]})
        return _loaded[1]
```

and in the handler: `m = model()` once, `version = m["version"]`, and
`print(f"predict {code} version={version}")`.

## Details worth knowing

- **`ln -sfn` is not atomic.** It deletes the link and then creates a new one, and
  a reader in that instant finds nothing. `check.sh` usually can't catch a gap
  that short, but production traffic eventually will. `mv -T` (GNU), `os.replace`,
  or Kubernetes swapping which Deployment a Service points at are the atomic versions.
- **Keep the bad version.** Rollback flips the pointer and deletes nothing. v2 is
  evidence: you need it to find out what was wrong, and to re-deploy once fixed.
- **Version every log line, and more.** In production you'd also log the model's
  hash (so "v2" can't silently mean two different files), and record the version
  next to each stored prediction so affected decisions can be found and redone.
- **This is the same move as blue/green deploys** and Kubernetes rollouts:
  never edit what's serving, stand up the complete new thing, then switch traffic
  in one step. Model registries (MLflow's model aliases, SageMaker endpoints) are
  this pattern with a UI and an audit log.
- **What this doesn't cover:** several replicas. Each one flips at a slightly
  different moment, so for a few seconds the *fleet* serves both versions.
  Responses still each come from one complete version, which is what matters, but
  dashboards must group by version to make sense of it.
