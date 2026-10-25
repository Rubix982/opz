#!/usr/bin/env bash
# Builds the production image twice, from "PyPI" as it looked today and as it
# will look next week, plus once from a compromised mirror. Passes only when:
#   - both builds run and reproduce the paper's numbers (app/expected.json)
#   - both builds installed exactly the same packages, indirect ones included
#   - the build refuses packages whose contents changed under the same version
#   - the base image is pinned to an exact digest, not a moving tag
set -u
cd "$(dirname "$0")"
fail=0
: > .check.log
[ -d index/2026-10-25 ] || { echo "run ./setup.sh first"; exit 1; }
trap 'docker rmi -f opz-lab26-today opz-lab26-nextweek opz-lab26-tampered >/dev/null 2>&1; rm -rf .check-ctx' EXIT

build() {  # tag, index-dir, context
  docker build --progress=plain -f "$3/app/Dockerfile" --build-arg INDEX="$2" -t "$1" "$3" >>.check.log 2>&1
}
expected=$(python3 -c "import json; print(json.dumps(json.load(open('app/expected.json')), sort_keys=True))")
result() { docker run --rm "$1" 2>>.check.log | python3 -c "import json,sys; print(json.dumps(json.loads(sys.stdin.read()), sort_keys=True))" 2>/dev/null; }

for when in today:2026-10-25 nextweek:2026-11-01; do
  tag=opz-lab26-${when%%:*}; date=${when##*:}
  if ! build $tag index/$date .; then echo "FAIL  build from the $date index failed (see .check.log)"; fail=1; continue; fi
  out=$(result $tag)
  if [ "$out" = "$expected" ]; then echo "pass  build from the $date index reproduces the paper's numbers"
  elif [ -z "$out" ]; then echo "FAIL  build from the $date index: train.py crashed: $(docker run --rm $tag 2>&1 | tail -1)"; fail=1
  else echo "FAIL  build from the $date index gives different numbers: $out"; fail=1; fi
done

a=$(docker run --rm opz-lab26-today pip freeze 2>/dev/null); b=$(docker run --rm opz-lab26-nextweek pip freeze 2>/dev/null)
if [ -n "$a" ] && [ "$a" = "$b" ]; then echo "pass  same packages a week apart: $(echo $a)"
else echo "FAIL  packages differ a week apart: [$(echo $a)] vs [$(echo $b)]"; fail=1; fi

mkdir -p .check-ctx && rsync -a --exclude '.venv*' --exclude .check-ctx --exclude .check.log ./ .check-ctx/
python3 tools/make_index.py --tamper .check-ctx/index/2026-10-25
if build opz-lab26-tampered index/2026-10-25 .check-ctx; then echo "FAIL  build accepted packages whose contents changed (nothing verifies them)"; fail=1
else echo "pass  build refuses tampered packages ($(grep -m1 -o "DO NOT MATCH THE HASHES" .check.log || echo "see .check.log"))"; fi

if grep -qE '^FROM [^ ]+@sha256:[0-9a-f]{64}' app/Dockerfile; then echo "pass  base image pinned by digest"
else echo "FAIL  base image is a moving tag: $(grep -m1 '^FROM' app/Dockerfile)"; fail=1; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
