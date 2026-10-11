"""Framework mass ratchet (ADR-0057) — mass may only go down.

Four numbers: framework source lines, test lines, in-tree documentation lines,
and top-level DSL construct count. `tests/unit/test_mass_ratchet.py` fails the
Tier 0 gate when any current value exceeds the committed baseline. The baseline
is rewritten downward with `--write-baseline`; raising any value needs
`--force --reason "..."`, which is recorded in the baseline so the exception
is visible in history.

Usage:
    uv run python scripts/mass_ratchet.py --status
    uv run python scripts/mass_ratchet.py --write-baseline
    uv run python scripts/mass_ratchet.py --write-baseline --force --reason "…"
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "tests" / "unit" / "fixtures" / "mass_baseline.json"
PARSER_INIT = REPO / "src" / "dazzle" / "core" / "dsl_parser_impl" / "__init__.py"
_SKIP = {"node_modules", ".venv", "__pycache__", ".git"}
METRICS = ("src_lines", "test_lines", "docs_lines", "construct_count")


def _tracked(root: Path, suffix: str) -> list[Path]:
    """Git-tracked files under ``root`` with ``suffix`` — the same set CI sees."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", str(root)], cwd=REPO, capture_output=True, check=True
    ).stdout
    # A file deleted in the worktree but not yet staged is still listed; skip it.
    return [
        REPO / p for p in out.decode().split("\0") if p.endswith(suffix) and (REPO / p).is_file()
    ]


def _lines(root: Path, suffix: str) -> int:
    return sum(sum(1 for _ in p.open("rb")) for p in _tracked(root, suffix))


def measure() -> dict[str, int]:
    text = PARSER_INIT.read_text(encoding="utf-8")
    constructs = set(re.findall(r"TokenType\.[A-Z_]+:\s*self\._dispatch_([a-z_]+)", text)) | {"app"}
    return {
        "src_lines": _lines(REPO / "src" / "dazzle", ".py"),
        "test_lines": _lines(REPO / "tests", ".py"),
        "docs_lines": _lines(REPO / "docs", ".md"),
        "construct_count": len(constructs),
    }


def load_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def compare(current: dict[str, int], baseline: dict) -> list[str]:
    """Human-readable regressions; empty means the ratchet holds."""
    return [
        f"{m}: {current[m]:,} > baseline {baseline[m]:,} (+{current[m] - baseline[m]:,})"
        for m in METRICS
        if current[m] > baseline[m]
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--force", action="store_true", help="allow a value to rise (needs --reason)")
    ap.add_argument("--reason", default="")
    args = ap.parse_args(argv)
    current = measure()
    if args.write_baseline:
        prev = load_baseline() if BASELINE.exists() else {}
        rises = [m for m in METRICS if m in prev and current[m] > prev[m]]
        if rises and not (args.force and args.reason.strip()):
            print(
                "REFUSED: baseline may only fall — rising: "
                + ", ".join(f"{m} {prev[m]:,}→{current[m]:,}" for m in rises)
                + ". Retire mass, or --force --reason '…'.",
                file=sys.stderr,
            )
            return 1
        data = {**current, "written": _dt.date.today().isoformat()}
        if rises:
            data["exceptions"] = [
                *prev.get("exceptions", []),
                {"date": data["written"], "rose": rises, "reason": args.reason.strip()},
            ]
        elif "exceptions" in prev:
            data["exceptions"] = prev["exceptions"]
        BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE.relative_to(REPO)}: {current}")
        return 0
    baseline = load_baseline() if BASELINE.exists() else None
    for m in METRICS:
        b = f"{baseline[m]:,}" if baseline else "—"
        print(f"{m:16} current {current[m]:>9,}   baseline {b:>9}")
    if baseline:
        regressions = compare(current, baseline)
        print("\n".join(regressions) if regressions else "OK mass ratchet holds")
        return 1 if regressions else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
