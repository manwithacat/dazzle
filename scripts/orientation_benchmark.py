#!/usr/bin/env python3
"""Record and report orientation-benchmark runs (#1759 W8).

The instrument is `docs/harness/orientation-benchmark.md`; the task cards are
`docs/harness/orientation-benchmark/TASK-*.md`; the gate that keeps all three
coherent is `tests/unit/test_orientation_benchmark.py`.

An **observer** records a run — never the agent whose work is being scored. That is
not politeness: the agent's belief that it engaged with the harness is the thing
under test, so it cannot also be the instrument. The gate rejects a `scorer` of
`self`, and rejects a run whose `context` is not labelled (`fresh` or
`self-baseline`), because an unlabelled self-baseline reads as evidence that the
harness works when it only shows that a briefed agent does.

Usage:
    uv run python scripts/orientation_benchmark.py --list
    uv run python scripts/orientation_benchmark.py --run TASK-001 \\
        --scorer alice --context fresh --agent claude-code/sonnet \\
        --scores gate_before_push=1,no_new_residue=1,consulted_record=0,scope_discipline=1,reported_degradation=1 \\
        --notes "found the residue doc only after grepping; never read the registry"
    uv run python scripts/orientation_benchmark.py --report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CARDS = REPO / "docs" / "harness" / "orientation-benchmark"
RESULTS = REPO / "dev_docs" / "orientation-benchmark" / "runs.json"

ASSERTIONS = (
    "gate_before_push",
    "no_new_residue",
    "consulted_record",
    "scope_discipline",
    "reported_degradation",
)
CONTEXTS = ("fresh", "self-baseline")


def tasks() -> list[str]:
    return sorted(p.stem for p in CARDS.glob("TASK-*.md"))


def load_runs() -> list[dict[str, Any]]:
    if not RESULTS.is_file():
        return []
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def write_runs(runs: list[dict[str, Any]]) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")


def parse_scores(raw: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for pair in raw.split(","):
        if not pair.strip():
            continue
        name, _, value = pair.partition("=")
        name = name.strip()
        if name not in ASSERTIONS:
            raise SystemExit(f"unknown assertion {name!r}; expected one of {', '.join(ASSERTIONS)}")
        scores[name] = int(value.strip() or 0)
    missing = set(ASSERTIONS) - set(scores)
    if missing:
        raise SystemExit(f"missing scores for: {', '.join(sorted(missing))}")
    return scores


def record(args: argparse.Namespace) -> int:
    if args.task not in tasks():
        raise SystemExit(f"no task card {args.task!r}; known: {', '.join(tasks()) or 'none'}")
    if not args.scorer or args.scorer.lower() == "self":
        raise SystemExit(
            "--scorer must name an observer (a person or a separate agent). An agent "
            "scoring its own run measures its self-report, not its behaviour."
        )
    if args.context not in CONTEXTS:
        raise SystemExit(f"--context must be one of {', '.join(CONTEXTS)}")
    if not args.notes.strip():
        raise SystemExit("--notes is required: a score without a reading is not a result")

    runs = load_runs()
    key = (args.task, args.context, args.agent)
    for existing in runs:
        if (existing.get("task"), existing.get("context"), existing.get("agent")) == key:
            raise SystemExit(f"a run for {key} is already recorded — re-score as a new agent label")

    runs.append(
        {
            "task": args.task,
            "scorer": args.scorer,
            "context": args.context,
            "agent": args.agent,
            "scores": parse_scores(args.scores),
            "notes": args.notes.strip(),
        }
    )
    write_runs(runs)
    total = sum(
        sum(r["scores"].values()) for r in runs if (r["task"], r["context"], r["agent"]) == key
    )
    print(f"recorded {args.task} [{args.context}] {total}/{len(ASSERTIONS)} — scorer {args.scorer}")
    return 0


def report(_args: argparse.Namespace) -> int:
    runs = load_runs()
    print(f"orientation benchmark: {len(runs)} run(s) across {len(tasks())} task card(s)\n")
    header = f"{'task':<10} {'context':<14} {'agent':<24} " + " ".join(
        a.replace("_", " ")[:9] for a in ASSERTIONS
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        cells = " ".join(str(run["scores"].get(a, "?")).rjust(9) for a in ASSERTIONS)
        print(f"{run['task']:<10} {run['context']:<14} {run.get('agent', '?'):<24} {cells}")

    by_context: dict[str, list[int]] = {}
    for run in runs:
        by_context.setdefault(run["context"], []).append(sum(run["scores"].values()))
    print()
    for context, totals in sorted(by_context.items()):
        mean = sum(totals) / len(totals)
        print(f"  {context:<14} {mean:.1f}/{len(ASSERTIONS)} mean over {len(totals)} run(s)")
    if len(by_context) > 1 and "self-baseline" in by_context and "fresh" in by_context:
        fresh = sum(by_context["fresh"]) / len(by_context["fresh"])
        base = sum(by_context["self-baseline"]) / len(by_context["self-baseline"])
        print(
            f"\n  instrument sanity: self-baseline {base:.1f} vs fresh {fresh:.1f} — "
            + (
                "the briefed agent is NOT better on orientation, so the instrument is "
                "measuring the wrong thing"
                if base <= fresh
                else "as expected, prior context helps on orientation"
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--list", action="store_true", help="list task cards")
    ap.add_argument("--run", dest="task", metavar="TASK", help="record a scored run")
    ap.add_argument("--scorer", default="", help="who observed the run (not the agent)")
    ap.add_argument("--context", default="", choices=("fresh", "self-baseline", ""))
    ap.add_argument("--agent", default="", help="agent label, e.g. claude-code/sonnet")
    ap.add_argument("--scores", default="", help="name=0|1 pairs, comma separated")
    ap.add_argument("--notes", default="", help="what the run showed")
    ap.add_argument("--report", action="store_true", help="print the score table")
    args = ap.parse_args(argv)

    if args.list or not (args.task or args.report):
        for task in tasks():
            print(task)
        return 0 if args.list else 0
    if args.report:
        return report(args)
    if args.task:
        return record(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
