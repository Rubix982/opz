#!/usr/bin/env bash
# Starts a fresh copy of the API on port 18027, then:
#   - an honest customer scores 200 real applications: all must be served and correct
#   - responses must not hand out the per-class probabilities
#   - a bulk partner sends 1,500 in a day: they must be cut off by a per-key budget
#   - the rival runs the extraction attack with a 3,000-query budget: the stolen
#     copy must agree with the real model on under 80% of genuine applications
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
[ -x $PY ] || { echo "run ./setup.sh first"; exit 1; }
PORT=18027
export API_URL="http://127.0.0.1:$PORT"
fail=0

if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then echo "port $PORT is busy (an old server?): lsof -iTCP:$PORT"; exit 1; fi
(cd app && PORT=$PORT exec ../$PY server.py) >.check.log 2>&1 & srv=$!
trap 'kill $srv 2>/dev/null; wait $srv 2>/dev/null' EXIT
for _ in $(seq 1 100); do curl -s -o /dev/null "$API_URL/" && break; sleep 0.2; done

field() { $PY -c "import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2]))" "$1" "$2"; }

honest=$($PY tools/honest_client.py --key key_FAKE_acme --n 200)
served=$(field "$honest" 'd["served"]'); correct=$(field "$honest" 'd["correct"]')
if [ "$served" = 200 ] && [ "$correct" = 200 ]; then echo "pass  honest customer: 200/200 served, all decisions correct"
else echo "FAIL  honest customer: $served/200 served, $correct correct"; fail=1; fi

# Count the fractional numbers in a real response: one coarse score is fine,
# a probability per class is what makes the model cheap to copy.
leaks=$(field "$honest" '(lambda f: f(f, d["example_response"]))(lambda f, v: sum(f(f, x) for x in (v.values() if isinstance(v, dict) else v)) if isinstance(v, (dict, list)) else int(isinstance(v, float) and not v.is_integer()))')
if [ "$leaks" -le 1 ]; then echo "pass  responses don't include the per-class probabilities"
else echo "FAIL  responses include $leaks probabilities: $(field "$honest" 'd["example_response"]')"; fail=1; fi

bulk=$($PY tools/honest_client.py --key key_FAKE_bulk --n 1500 --seed 2)
refusal=$(field "$bulk" 'd["first_refusal"]')
if [ "$refusal" != None ]; then echo "pass  per-key budget: bulk partner cut off at query $(field "$bulk" 'd["first_refusal"]["at"]') of 1500"
else echo "FAIL  no per-key budget: one key got 1500 answers in a day"; fail=1; fi

attack=$($PY tools/extract.py --key key_FAKE_rival --budget 3000)
agree=$(field "$attack" 'd["agreement"]')
echo "      attack: $attack"
if $PY -c "import sys; sys.exit(0 if $agree < 0.80 else 1)"; then echo "pass  stolen copy agrees on only $(field "$attack" 'round(d["agreement"]*100)')% of real applications"
else echo "FAIL  stolen copy agrees with the real model on $(field "$attack" 'round(d["agreement"]*100)')% of real applications"; fail=1; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
