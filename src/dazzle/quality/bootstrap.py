"""Write tooling-file templates into an existing Dazzle project.

For fresh `dazzle init` flows the blank template already ships these files.
This module handles the existing-project case: it reads what's there, swaps
in the Dazzle-managed tables, and leaves everything else alone.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w


def _template_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "blank"


def _load_template_ruff_tables() -> dict[str, Any]:
    """Read the Dazzle-managed [tool.ruff*] tables out of the blank template."""
    template = _template_dir() / "pyproject.toml"
    return tomllib.loads(template.read_text(encoding="utf-8"))


def quality_bootstrap(project_dir: Path) -> list[Path]:
    """Write the three tooling files into `project_dir`.

    pyproject.toml: replace [tool.ruff*] tables, leave others.
    pyrightconfig.json: write if missing, replace if present.
    .pre-commit-config.yaml: write if missing, leave alone if present.

    Returns the list of files written (or rewritten).
    """
    project_dir = project_dir.resolve()
    written: list[Path] = []

    written.extend(_bootstrap_pyproject(project_dir))
    written.extend(_bootstrap_pyright(project_dir))
    written.extend(_bootstrap_precommit(project_dir))

    return written


def _bootstrap_pyproject(project_dir: Path) -> list[Path]:
    """Replace [tool.ruff*] tables in pyproject.toml; preserve other tables.

    Note: tomli_w cannot re-emit TOML comments, so the
    `# managed-by: dazzle quality bootstrap` header from the blank template
    appears in fresh `dazzle init` output (verbatim file copy) but not in
    `dazzle quality bootstrap` output against an existing project (re-parsed
    and re-serialised). The CLI hint text after bootstrap is the ownership
    signal in that case.
    """
    target = project_dir / "pyproject.toml"
    template_tables = _load_template_ruff_tables()

    if target.exists():
        existing = tomllib.loads(target.read_text(encoding="utf-8"))
    else:
        existing = {}

    # Replace tool.ruff wholesale (we own it).
    tool = existing.setdefault("tool", {})
    tool["ruff"] = template_tables["tool"]["ruff"]

    target.write_text(tomli_w.dumps(existing), encoding="utf-8")
    return [target]


def _bootstrap_pyright(project_dir: Path) -> list[Path]:
    target = project_dir / "pyrightconfig.json"
    src = _template_dir() / "pyrightconfig.json"
    target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return [target]


def _bootstrap_precommit(project_dir: Path) -> list[Path]:
    target = project_dir / ".pre-commit-config.yaml"
    if target.exists():
        return []  # don't overwrite a user-customised pre-commit config
    src = _template_dir() / ".pre-commit-config.yaml"
    target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return [target]
