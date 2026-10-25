# Lab 25 · Improper Rollback

**Track C, AI pipelines** · **Time:** ~40 min · **Needs:** Python 3 (standard library only)

## The incident

Model v2 went out this morning and its scores are off, so on-call rolled back
to v1 the usual way: `./deploy.sh v1`, which copies v1's files into
`models/current/` while the service keeps running. It reloads files when they
change, so no restart is needed.

During the rollback:
- hundreds of requests got **500s**;
- some requests got a **score that neither v1 nor v2 would produce**;
- afterwards nobody could say from the logs which model answered which request,
  so finance couldn't tell which of the morning's decisions to redo.

A model version is two files that only make sense together: `preprocess.json`
(how inputs are scaled) and `weights.json` (the model trained on inputs scaled
that way).

## Setup

```bash
./setup.sh               # v2 live, the state before the rollback
python3 app.py           # terminal 1: the service on 127.0.0.1:8025
python3 -c "import json,random; print(json.dumps({'x':[random.uniform(-2,2) for _ in range(600)]}))" > /tmp/x.json
curl -s -XPOST localhost:8025/predict -d @/tmp/x.json
./deploy.sh v1           # the rollback; hammer the service while it runs
```

## Your job

1. **Explain each symptom** before fixing anything. Hints, one at a time:
   - Read `tools/copy_files.py`. What does `models/current/` look like halfway
     through? What does `app.py` read at that moment?
   - Two kinds of bad state are possible mid-copy. One gives a 500. Which one gives
     a *wrong answer* with a 200?
   - What would a log line need to contain to answer "which model scored request X?"
2. **Fix `deploy.sh` and `app.py`.** The rollback must never expose a half-copied
   or mixed model, and every log line must say which version served it. Hints:
   - The version directories `models/v1/` and `models/v2/` are complete and never
     edited. Could "live" be a *pointer* to one of them instead of a copy?
   - Look up which filesystem operation is atomic: `os.replace` / rename(2).
   - Inside the service, make sure one request uses one model from start to finish.
3. **Prove it.** `./check.sh` puts v2 live, sends steady traffic from 4 threads,
   rolls back to v1 in the middle, and checks every response and log line.
4. **Write the retro** (below). Run `./setup.sh` to reset any time.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why copying files over a live version fails, both ways it fails:
- What makes a pointer swap safe (the two properties it needs):
- Why every log line needs the version, and what else it should carry in production:
- Why the bad version (v2) must be kept after a rollback:
- What a model registry (MLflow, etc.) adds on top of this:
