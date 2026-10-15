"""Jinja2 must not regrow in the framework (#1042/#1044, ADR-0023).

Rendering is the typed Fragment substrate. Jinja2 was dropped as a dependency in
v0.67.92 and ``src/dazzle/page/templates/`` was deleted with the last template.
This gate scans all of ``src/dazzle`` (not a list of migrated modules, which
could only miss a new file) for a jinja2 import or a call to the retired Jinja
entry points, and keeps the template tree and the dependency gone.

If it fails, render through the typed substrate instead; a deliberate return to
Jinja is an ADR-0023 change with a CHANGELOG entry, not an allowlist edit.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "dazzle"

_JINJA_PATTERNS = (
    re.compile(r"^\s*import\s+jinja2\b"),
    re.compile(r"^\s*from\s+jinja2\b"),
    re.compile(r"\brender_site_page\("),
    re.compile(r"\brender_fragment\("),
    re.compile(r"\bdef build_site_(auth|404|error)_context\("),
)


def test_no_jinja_in_framework_source() -> None:
    hits: list[str] = []
    files = sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)
    assert len(files) > 100, "scan found too few modules; SRC is probably wrong"
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(pattern.search(line) for pattern in _JINJA_PATTERNS):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not hits, "Jinja2 regrowth in the typed runtime:\n  " + "\n  ".join(hits)


def test_template_tree_and_dependency_stay_gone() -> None:
    templates = SRC / "page" / "templates"
    assert not templates.exists(), (
        f"{templates.relative_to(ROOT)} reappeared; page chrome is typed-Fragment views now"
    )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = list(project["dependencies"]) + [
        dep for extra in project.get("optional-dependencies", {}).values() for dep in extra
    ]
    assert not [d for d in declared if d.lower().startswith("jinja2")], (
        "jinja2 is a declared dependency again"
    )
