# Lab 26 · Environment Drift

**Time:** ~40 min · **Needs:** Docker, Python 3 · **Cost:** free, all local, works offline

## The incident

A researcher trained the house-price model on their laptop last month. The
weights are in the paper's Table 2 (`app/expected.json`). Today the team
built the production image from the same code and it crashed on startup with an
`ImportError`. Someone "fixed" that by pinning the library that broke, and now
the image runs, but its numbers no longer match the paper. Nobody changed the code.

## Setup

```bash
./setup.sh                                   # builds the lab's package index and the laptop's venv
.venv-laptop/bin/python app/train.py         # the laptop: matches app/expected.json
.venv-laptop/bin/pip freeze

docker build -f app/Dockerfile -t opz-lab26 . && docker run --rm opz-lab26   # production, today
docker run --rm opz-lab26 pip freeze
```

There's no internet involved. `index/` stands in for PyPI as it looked on three
dates (`tools/make_index.py` documents every release):

| Folder | What had been released by then |
|---|---|
| `index/2026-09-20/` | when the laptop was set up |
| `index/2026-10-25/` | today (the Dockerfile's default) |
| `index/2026-11-01/` | next week |

Build "next week" with `--build-arg INDEX=index/2026-11-01`.

## Your job

1. **Diagnose.** Compare the laptop and the image. Hints, one at a time:
   - `pip freeze` in both. What differs, and which of those packages did *you* ask for?
   - Read `app/requirements.txt`. What does `>=` promise about next week's build?
   - Pin only `featurekit==1.4.0` and rebuild. Does the import error go away? Do the
     numbers match the paper? Which package changed underneath you, and who
     depends on it?
2. **Make builds reproducible.**
   - Lock **every** package, indirect ones included, to the exact versions that
     produced the paper's numbers. Real tools: `uv pip compile`, `pip-compile`
     (pip-tools), `poetry lock`. Here, `pip freeze` from the laptop plus
     `pip hash <wheel>` is enough.
   - A version number is a name, not a promise about contents. How do you make
     pip refuse a file whose contents changed? (`--require-hashes`)
   - `python:3.12-slim` is a tag that moves when a new patch release ships. How
     do you pin the base image exactly? (`docker inspect python:3.12-slim --format '{{index .RepoDigests 0}}'`)
3. **Prove it.** `./check.sh` builds from today's index, next week's, and a
   compromised mirror where every package was swapped for a modified one with the
   same version. It passes only when both real builds reproduce the paper,
   install identical packages, the tampered build is refused, and the base image
   is pinned by digest.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why the build that worked last month breaks today with no code change:
- The two kinds of drift here (loud and silent), and which is worse:
- Why pinning only my direct dependency wasn't enough:
- What a hash adds that a version pin doesn't:
- What a lockfile still doesn't pin (OS packages, Python itself, hardware):
