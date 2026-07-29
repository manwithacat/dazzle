#!/usr/bin/env python3
"""CLI: work-surface utility ontology + example-app fit residual.

Usage::

    python scripts/work_surface_utility.py --list
    python scripts/work_surface_utility.py --app simple_task
    python scripts/work_surface_utility.py --fleet
    python scripts/work_surface_utility.py --measurement

Exit 0 always for --list/--measurement; --fleet/--app exit 1 only with --strict
when residual > 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from dazzle.qa.work_surface_utility import (  # noqa: E402
    load_ontology,
    residual,
    scan_project,
    summary,
    surfaces_from_ontology,
)


def _examples() -> list[Path]:
    root = REPO / "examples"
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "dsl").is_dir())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="Print ontology surfaces")
    ap.add_argument("--measurement", action="store_true", help="Print measurement method")
    ap.add_argument("--app", help="Example app name under examples/")
    ap.add_argument("--fleet", action="store_true", help="Scan all example apps with dsl/")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when residual > 0 (unknown/missing ontology)",
    )
    args = ap.parse_args(argv)

    if args.list:
        surfaces = surfaces_from_ontology()
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "id": s.id,
                            "job": s.job,
                            "utility_axes": list(s.utility_axes),
                            "measure_proxy": s.measure_proxy,
                        }
                        for s in surfaces
                    ],
                    indent=2,
                )
            )
        else:
            print(f"work_surface_utility n={len(surfaces)}")
            for s in surfaces:
                print(f"  {s.id:16} axes={','.join(s.utility_axes)}")
                print(f"    job: {s.job}")
        return 0

    if args.measurement:
        data = load_ontology()
        m = data.get("measurement") or {}
        if args.json:
            print(json.dumps(m, indent=2))
        else:
            print(m.get("method", "").strip())
            print("\nsuccess_criteria:")
            for c in m.get("success_criteria") or []:
                print(f"  - {c}")
        return 0

    findings = []
    if args.app:
        project = REPO / "examples" / args.app
        if not project.is_dir():
            print(f"unknown app: {args.app}", file=sys.stderr)
            return 2
        findings = scan_project(project, app_name=args.app)
    elif args.fleet:
        for p in _examples():
            findings.extend(scan_project(p, app_name=p.name))
    else:
        ap.print_help()
        return 2

    sm = summary(findings)
    if args.json:
        print(
            json.dumps(
                {"summary": sm, "findings": [f.to_json() for f in findings]},
                indent=2,
            )
        )
    else:
        print(
            f"work_surface_utility count={sm['count']} residual={sm['residual']} "
            f"by_status={sm['by_status']} by_ontology={sm['by_ontology']}"
        )
        for f in findings:
            if f.status != "matched":
                print(
                    f"  ! {f.app}/{f.surface_name} display={f.display!r} {f.status}: {f.description}"
                )
        # matched one-liner sample
        matched = [f for f in findings if f.status == "matched"]
        if matched and not args.fleet:
            print("matched:")
            for f in matched[:20]:
                print(f"  · {f.surface_name} → {f.ontology_id}")

    if args.strict and residual(findings) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
