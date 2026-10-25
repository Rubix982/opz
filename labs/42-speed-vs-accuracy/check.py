"""Checks the decision record for lab 42. Run through ./check.sh. Standard library only."""

import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# The product constraints, as stated in the README.
MAX_P95_MS = 300
MIN_ACCURACY = 0.90
MAX_COST_PER_1K = 0.40

SECTIONS = ["Context", "Constraints", "Options considered", "Decision", "Trade-offs accepted", "Revisit if"]

results: list[tuple[bool, str]] = []


def report(ok: bool, msg: str) -> None:
    results.append((ok, msg))


def load_variants() -> dict[str, dict]:
    with open(os.path.join(HERE, "data", "benchmarks.csv")) as f:
        rows = list(csv.DictReader(f))
    return {
        r["variant"]: {
            "p95": float(r["p95_ms"]),
            "acc": float(r["accuracy"]),
            "cost": float(r["cost_per_1k_usd"]),
        }
        for r in rows
    }


def feasible(v: dict) -> list[str]:
    """The constraints a variant breaks (empty list = meets them all)."""
    broken = []
    if v["p95"] > MAX_P95_MS:
        broken.append(f"p95 {v['p95']:.0f} ms > {MAX_P95_MS} ms")
    if v["acc"] < MIN_ACCURACY:
        broken.append(f"accuracy {v['acc']:.3f} < {MIN_ACCURACY:.2f}")
    if v["cost"] > MAX_COST_PER_1K:
        broken.append(f"cost ${v['cost']:.2f}/1k > ${MAX_COST_PER_1K:.2f}/1k")
    return broken


def dominates(a: dict, b: dict) -> bool:
    """a is at least as good as b on p95, accuracy and cost, and better on one."""
    at_least = a["p95"] <= b["p95"] and a["acc"] >= b["acc"] and a["cost"] <= b["cost"]
    better = a["p95"] < b["p95"] or a["acc"] > b["acc"] or a["cost"] < b["cost"]
    return at_least and better


def sections(md: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current = None
    for line in md.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1)
            out[current] = ""
        elif current is not None:
            out[current] += line + "\n"
    return out


def main() -> int:
    variants = load_variants()

    # --- decision.json -------------------------------------------------------
    try:
        with open(os.path.join(HERE, "decision.json")) as f:
            d = json.load(f)
        report(True, "decision.json parses")
    except (OSError, json.JSONDecodeError) as e:
        report(False, f"decision.json doesn't parse: {e}")
        d = {}

    choice = d.get("choice", "")
    v = variants.get(choice)
    if v is None:
        report(False, f"choice {choice!r} isn't a variant in data/benchmarks.csv")
    else:
        report(True, f"choice {choice!r} is a real variant")
        broken = feasible(v)
        report(not broken, f"{choice} meets every hard constraint" if not broken
               else f"{choice} breaks a hard constraint: {'; '.join(broken)}")

        claimed = (d.get("expected_p95_ms"), d.get("expected_accuracy"), d.get("cost_per_1k_usd"))
        try:
            ok = (abs(float(claimed[0]) - v["p95"]) <= 1 and abs(float(claimed[1]) - v["acc"]) <= 0.0015
                  and abs(float(claimed[2]) - v["cost"]) <= 0.005)
        except (TypeError, ValueError):
            ok = False
        report(ok, "expected p95, accuracy and cost match the benchmarks" if ok else
               f"expected numbers {claimed} don't match the benchmark row "
               f"({v['p95']:.0f} ms, {v['acc']:.3f}, ${v['cost']:.2f})")

    triggers = d.get("revisit_if", [])
    concrete = [t for t in triggers if isinstance(t, str) and re.search(r"\d", t)]
    report(len(triggers) >= 2 and len(concrete) == len(triggers),
           f"{len(triggers)} revisit triggers, each with a number" if len(triggers) >= 2 and len(concrete) == len(triggers)
           else "need at least 2 revisit triggers in decision.json, each measurable (containing a number)")

    # --- DECISION.md ---------------------------------------------------------
    with open(os.path.join(HERE, "DECISION.md")) as f:
        md = f.read()
    secs = sections(md)
    missing = [s for s in SECTIONS if s not in secs]
    empty = [s for s in SECTIONS if s in secs and len(re.findall(r"\w+", secs[s])) < 8]
    placeholder = "Replace this" in md
    ok = not missing and not empty and not placeholder
    report(ok, "DECISION.md: every section written" if ok else
           "DECISION.md: " + "; ".join(filter(None, [
               f"missing {missing}" if missing else "",
               f"too short or empty: {empty}" if empty else "",
               "placeholder text left ('Replace this')" if placeholder else "",
           ])))

    cons = secs.get("Constraints", "")
    has_targets = ("300" in cons and re.search(r"0?\.90\b|90\s?%", cons) is not None
                   and re.search(r"0?\.40\b|40\s?(cents|¢)", cons) is not None)
    report(has_targets, "Constraints states the latency target, accuracy floor and cost ceiling"
           if has_targets else "Constraints must state the p95 target (300 ms), accuracy floor (0.90) and cost ceiling ($0.40/1k)")

    opts = secs.get("Options considered", "")
    named = [name for name in variants if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", opts)]
    numbers = re.findall(r"\d+(?:\.\d+)?", opts)
    ok = len(named) >= 2 and len(numbers) >= 6
    report(ok, f"Options considered compares {len(named)} variants with numbers" if ok
           else f"Options considered names {len(named)} variant(s) and {len(numbers)} numbers; "
                "compare at least two variants, each with its p95, accuracy and cost")

    # --- Pareto check --------------------------------------------------------
    if v is not None and not feasible(v):
        better = [n for n, w in variants.items() if n != choice and not feasible(w) and dominates(w, v)]
        if not better:
            report(True, f"{choice} isn't beaten on every axis by another option that also meets the constraints")
        else:
            unexplained = [n for n in better if not re.search(rf"^#+\s*Why not {re.escape(n)}\b", md, re.M)]
            report(not unexplained,
                   f"{choice} is dominated by {better}, and DECISION.md explains why not" if not unexplained else
                   f"{', '.join(unexplained)} is at least as good as {choice} on p95, accuracy and cost, and also "
                   f"meets the constraints; pick it, or add a '## Why not {unexplained[0]}' section")

    failed = 0
    for ok, msg in results:
        print(f"{'pass' if ok else 'FAIL'}  {msg}")
        failed += not ok
    print("LAB PASSED" if not failed else "lab not passed yet")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
