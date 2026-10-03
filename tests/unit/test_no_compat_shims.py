r"""Deprecated aliases must not survive in the runtime (ADR-0003).

Why this exists
---------------
AGENTS.md and ADR-0003 both say **no backward-compat shims**: a clean break, with
all callers updated in the same commit. Shims were still accumulating because
nothing checked for them, and each one is a small liability:

- ``DatabaseManager`` was a \`type\` alias for \`PostgresBackend\` wrapped in a
  \`try/except ImportError\` that set it to \`Any\`. \`psycopg\` is a *core* dependency
  and \`PostgresBackend\` imports unconditionally, so the except branch was dead
  defensiveness whose only effect was to silently drop type checking to \`Any\`
  across seven modules if it ever did fire.
- ``ENGINE_HINT`` is a retired *grammar* keyword that still parses, so DSL written
  against it keeps working instead of failing loudly — the opposite of what
  ADR-0003 asks for.

What this catches
----------------
A module-level \`type X = Y\` or \`X = Y\` alias that exists only to preserve an
old name, and any remaining reference to a name on the retired list.

How to satisfy it
-----------------
Import the real name. If you need a deprecation, make it fail rather than
silently succeed.

What this does NOT catch
------------------------
A shim that is not an assignment — e.g. a re-export in \`__init__.py\`. Those are
covered by \`test_api_surface_drift.py\`, which would show the removal as drift
and require a CHANGELOG entry.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
_SRC = REPO / "src" / "dazzle"

# Name -> why it must not come back.
_RETIRED: dict[str, str] = {
    "DatabaseManager": (
        "retired alias for PostgresBackend (ADR-0008 made PostgreSQL the only "
        "backend). Was wrapped in try/except ImportError -> Any, which silently "
        "degraded typing across 7 modules."
    ),
}


def _alias_assignments(path: Path) -> list[tuple[int, str, str]]:
    """Module-level `X = Y` / `type X = Y` bindings."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found: list[tuple[int, str, str]] = []
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.TypeAlias) and node.value is not None:  # py3.12 `type X = Y`
            target, value = node.name, node.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Name):
            continue
        found.append((node.lineno, target.id, value.id))
    return found


def test_no_retired_compat_aliases() -> None:
    """A `type X = Y` whose only purpose is the old name must be gone."""
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, target, _value in _alias_assignments(path):
            if target in _RETIRED:
                offenders.append(f"{path.relative_to(REPO)}:{lineno} -> {target}")
    assert not offenders, (
        "Retired compat aliases are back. ADR-0003 requires a clean break with "
        "callers updated in the same commit:\n  " + "\n  ".join(offenders)
    )


def test_no_references_to_retired_names() -> None:
    """Nothing may reference a retired name either — an alias is only half a shim."""
    patterns = {name: re.compile(rf"\b{name}\b") for name in _RETIRED}
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, pat in patterns.items():
                if pat.search(line):
                    hits.append(f"{path.relative_to(REPO)}:{lineno} {name}")
    assert not hits, (
        "References to retired names remain — import the real name instead:\n  "
        + "\n  ".join(hits)
        + "\n\nRationale: "
        + "; ".join(f"{k}: {v}" for k, v in _RETIRED.items())
    )
