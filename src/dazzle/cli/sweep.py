"""`dazzle sweep examples` — unified validate + lint + coverage across
every example app.

Where `dazzle validate` / `dazzle lint` each inspect a single project,
``sweep examples`` walks every project under ``examples/*`` that has a
``dazzle.toml``, runs the standard gates, and emits a single report —
plus the framework-level ``dazzle coverage`` number, which only makes
sense across the repo as a whole.

Intended cadence: weekly, or after a parser/runtime change that might
regress example health. Output is stable enough to diff between runs.

Exit codes
----------
- 0: every app passed validate; no lint errors (warnings allowed).
- 1: at least one app produced a validate error or lint error.
- 2: fatal setup problem (e.g. cannot locate ``examples/``).

Usage
-----
    dazzle sweep examples            # human report
    dazzle sweep examples --json     # machine-readable
    dazzle sweep examples --strict   # treat warnings as failures
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer


@dataclass
class AppResult:
    name: str
    path: Path
    validate_ok: bool = True
    validate_output: str = ""
    lint_warnings: list[str] = field(default_factory=list)
    lint_errors: list[str] = field(default_factory=list)

    @property
    def has_lint_errors(self) -> bool:
        return bool(self.lint_errors)

    @property
    def has_any_finding(self) -> bool:
        return bool(self.lint_warnings or self.lint_errors) or not self.validate_ok


def _find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "examples").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate Dazzle repo root (expected pyproject.toml + examples/)."
    )


def _discover_example_apps(repo_root: Path) -> list[Path]:
    return sorted(
        d
        for d in (repo_root / "examples").iterdir()
        if d.is_dir() and (d / "dazzle.toml").is_file()
    )


def _run_gate(app_dir: Path, args: list[str]) -> tuple[int, str]:
    """Run ``dazzle <args>`` in ``app_dir``; return (exit_code, combined_output)."""
    proc = subprocess.run(
        ["python", "-m", "dazzle", *args],
        cwd=app_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, combined


def _parse_lint_output(text: str) -> tuple[list[str], list[str]]:
    """Split ``dazzle lint`` output into (errors, warnings).

    Skips lines that are known-benign preview-feature notices (those
    just list unimplemented-at-runtime features and aren't actionable).
    """
    errors: list[str] = []
    warnings: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("ERROR"):
            errors.append(line)
        elif line.startswith("WARNING"):
            if "[Preview]" in line:
                continue
            warnings.append(line)
    return errors, warnings


def _run_app(app_dir: Path) -> AppResult:
    result = AppResult(name=app_dir.name, path=app_dir)

    validate_code, validate_output = _run_gate(app_dir, ["validate"])
    result.validate_ok = validate_code == 0
    result.validate_output = validate_output

    _, lint_output = _run_gate(app_dir, ["lint"])
    errs, warns = _parse_lint_output(lint_output)
    result.lint_errors = errs
    result.lint_warnings = warns

    return result


def _coverage_snapshot(repo_root: Path) -> dict[str, Any]:
    """Capture the framework-artefact coverage numbers for the report."""
    from dazzle.cli.coverage import (
        _display_mode_coverage,
        _dsl_construct_coverage,
        _fragment_template_coverage,
    )

    cats = [
        _display_mode_coverage(repo_root),
        _dsl_construct_coverage(repo_root),
        _fragment_template_coverage(repo_root),
    ]
    return {
        cat.name: {
            "percent": round(cat.percent, 1),
            "covered": len(cat.covered),
            "total": len(cat.coverage),
            "uncovered": cat.uncovered,
        }
        for cat in cats
    }


def _render_human(results: list[AppResult], coverage: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Dazzle example-app sweep")
    lines.append("=" * 60)

    # Per-app summary table
    ok_count = sum(1 for r in results if not r.has_any_finding)
    lines.append(
        f"Apps: {len(results)}  |  Clean: {ok_count}  |  With findings: {len(results) - ok_count}"
    )
    lines.append("")
    lines.append(f"{'App':<22} {'Validate':<10} {'Lint err':<10} {'Lint warn':<10}")
    lines.append("-" * 60)
    for r in results:
        status = "OK" if r.validate_ok else "FAIL"
        lines.append(
            f"{r.name:<22} {status:<10} {len(r.lint_errors):<10} {len(r.lint_warnings):<10}"
        )
    lines.append("")

    # Per-app findings
    for r in results:
        if not r.has_any_finding:
            continue
        lines.append(f"## {r.name}")
        if not r.validate_ok:
            lines.append("  VALIDATE FAILED:")
            for line in r.validate_output.splitlines()[-8:]:
                if line.strip():
                    lines.append(f"    {line}")
        for err in r.lint_errors:
            lines.append(f"  ERROR: {err}")
        for warn in r.lint_warnings:
            lines.append(f"  WARN:  {warn}")
        lines.append("")

    # Coverage snapshot
    lines.append("## Framework-artefact coverage")
    for name, info in coverage.items():
        lines.append(f"  {name}: {info['covered']}/{info['total']} ({info['percent']:.0f}%)")
        if info["uncovered"]:
            lines.append(f"    uncovered: {', '.join(info['uncovered'])}")
    return "\n".join(lines)


def _render_json(results: list[AppResult], coverage: dict[str, Any]) -> str:
    payload: dict[str, Any] = {
        "apps": [
            {
                "name": r.name,
                "validate_ok": r.validate_ok,
                "lint_errors": r.lint_errors,
                "lint_warnings": r.lint_warnings,
            }
            for r in results
        ],
        "coverage": coverage,
    }
    return json.dumps(payload, indent=2)


def sweep_examples_command(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat lint warnings as failures (exit 1 if any app has a warning).",
    ),
) -> None:
    """Sweep every example app: validate + lint + framework coverage.

    Walks every project under ``examples/*/`` with a ``dazzle.toml``,
    runs ``dazzle validate`` and ``dazzle lint`` in each, and snapshots
    the framework-artefact coverage numbers for the repo as a whole.
    Emits a single report.
    """
    try:
        repo_root = _find_repo_root()
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    apps = _discover_example_apps(repo_root)
    if not apps:
        typer.echo("No example apps found under examples/.", err=True)
        raise typer.Exit(code=2)

    results = [_run_app(app) for app in apps]
    coverage = _coverage_snapshot(repo_root)

    if json_output:
        typer.echo(_render_json(results, coverage))
    else:
        typer.echo(_render_human(results, coverage))

    any_validate_fail = any(not r.validate_ok for r in results)
    any_lint_error = any(r.has_lint_errors for r in results)
    any_lint_warning = any(r.lint_warnings for r in results)

    if any_validate_fail or any_lint_error:
        sys.exit(1)
    if strict and any_lint_warning:
        sys.exit(1)
