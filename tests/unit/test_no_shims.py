"""Drift gate: no backward-compat shims in production code (ADR-0003).

Why this exists:
    ADR-0003 makes backward compatibility a non-goal: a clean break, with all
    callers updated in the same commit. Wrappers, aliases, re-exports and proxy
    modules kept only so an old call site keeps working accumulate, fragment
    the type surface and drift from the canonical implementation.

What this catches:
    * a comment that announces a shim (``# shim``, "backward-compatible shim");
    * a retired name coming back anywhere in ``src/`` or ``tests/`` — as a
      module-level alias (``X = Y`` / ``type X = Y``) or as any reference;
    * a deleted shim module re-created at its old path.

What this does NOT catch:
    A re-export in ``__init__.py`` under a new name. ``test_api_surface_drift.py``
    shows that as public-surface drift and requires a CHANGELOG entry.

How to satisfy:
    Delete the shim and import the real name. If a deprecation is needed, make
    it fail rather than silently succeed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "dazzle"
TESTS = REPO / "tests"
SELF = Path(__file__).resolve()

# Comments that strongly indicate a backward-compat shim.
_SHIM_MARKERS = (
    re.compile(r"#\s*shim\b", re.IGNORECASE),
    re.compile(r"backward[- ]compatible shim", re.IGNORECASE),
)

# A file where the marker is warning text about legacy state, not a wrapper.
_MARKER_ALLOWED = frozenset({"src/dazzle/rbac/matrix.py"})

# Name -> why it must not come back.
_RETIRED_NAMES: dict[str, str] = {
    "DatabaseManager": (
        "alias for PostgresBackend (ADR-0008 made PostgreSQL the only backend); its "
        "try/except ImportError -> Any silently dropped typing across 7 modules"
    ),
    "_fastapi_compat": "optional-import shim; FastAPI is a required core dependency",
    "FASTAPI_AVAILABLE": "dead guard flag of the FastAPI optional-import shim",
}

# Shim modules that were deleted; re-creating one re-introduces the shim layer.
_DELETED_SHIM_MODULES: dict[str, str] = {
    "src/dazzle/mcp/semantics.py": "pure re-export of dazzle.mcp.semantics_kb (#1008)",
    "src/dazzle/http/runtime/_fastapi_compat.py": "FastAPI optional-import shim",
}


def _py_files(*roots: Path) -> list[Path]:
    return [
        p
        for root in roots
        for p in sorted(root.rglob("*.py"))
        if "__pycache__" not in p.parts and p.resolve() != SELF
    ]


def test_no_backward_compat_shim_markers() -> None:
    """No production module may carry a `# shim` or `backward-compatible shim` marker."""
    offenders: list[str] = []
    for path in _py_files(SRC):
        rel = path.relative_to(REPO).as_posix()
        if rel in _MARKER_ALLOWED:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(marker.search(line) for marker in _SHIM_MARKERS):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Backward-compat shim markers are forbidden in production code (ADR-0003). "
        "Delete the wrapper, move the helper to its canonical location, or fix the "
        "comment if it is mislabelled:\n  " + "\n  ".join(offenders)
    )


def test_retired_names_stay_gone() -> None:
    """A retired name may not be defined, aliased or referenced again."""
    patterns = {name: re.compile(rf"\b{re.escape(name)}\b") for name in _RETIRED_NAMES}
    hits: list[str] = []
    for path in _py_files(SRC, TESTS):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pattern in patterns.items():
                if pattern.search(line):
                    hits.append(f"{path.relative_to(REPO)}:{lineno} {name}")
    assert not hits, (
        "Retired compat names are back; import the real name instead:\n  "
        + "\n  ".join(hits)
        + "\n\nWhy each is retired: "
        + "; ".join(f"{k}: {v}" for k, v in _RETIRED_NAMES.items())
    )


def test_deleted_shim_modules_stay_deleted() -> None:
    resurrected = [rel for rel in _DELETED_SHIM_MODULES if (REPO / rel).exists()]
    assert not resurrected, (
        "Deleted shim modules were re-created; update callers to import from the "
        f"canonical module instead: {resurrected}"
    )
