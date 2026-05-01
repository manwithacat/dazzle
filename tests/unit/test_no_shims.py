"""Drift gate: no backward-compat shim markers in production code.

Why this exists:
    ADR-0003 makes backward compatibility a non-goal at this stage. Wrapper
    functions, re-exports, and proxy modules created solely to keep an old
    API working are themselves a code smell — they accumulate, fragment the
    type surface, and drift from the canonical implementation.

What this catches:
    Comments that *announce* a backward-compat shim or wrapper. The presence
    of such a marker is a self-declared admission that the code exists only
    to preserve an old call site. Removing the underlying compatibility layer
    requires deleting both the wrapper and the marker.

What this does NOT catch:
    Genuine alias renames inside small, self-contained modules (e.g. enum
    aliases) that are part of an ongoing rename. Those are flagged by the
    explicit allow-list below.

How to satisfy:
    * Delete the shim and update all callers.
    * Move the helper to its canonical location and re-import there.
    * If the marker is mislabelled (the function isn't actually a shim),
      remove the marker comment.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROD_DIRS = ("src/dazzle", "src/dazzle_back", "src/dazzle_ui")

# Patterns that strongly indicate a backward-compat shim comment.
SHIM_PATTERNS = [
    re.compile(r"#\s*shim\b", re.IGNORECASE),
    re.compile(r"backward[- ]compatible shim", re.IGNORECASE),
]

# Files where a "backward compat" marker is a known, deliberate alias-rename
# rather than a removable wrapper. Each entry should reference an issue or
# ADR that pins the rename plan.
ALLOWED_PATHS: set[str] = {
    # LayoutArchetype = Stage rename — used pervasively in dazzle/ui/layout_engine.
    # Removing the alias is a multi-file rename tracked separately.
    "src/dazzle/core/ir/layout.py",
    "src/dazzle/core/ir/__init__.py",
    # Substantial API wrappers around dazzle.agent — refactor tracked separately.
    "src/dazzle/testing/agent_e2e.py",
    # RBAC backward-compat warning text describing PERMIT_UNPROTECTED legacy state.
    "src/dazzle/rbac/matrix.py",
}


def _walk_python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for d in PROD_DIRS:
        root = REPO_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            parts = p.relative_to(REPO_ROOT).parts
            if "tests" in parts:
                continue
            files.append(p)
    return files


def test_no_backward_compat_shim_markers() -> None:
    """No production module may carry a `# shim` or `backward-compatible shim` marker."""
    offenders: list[str] = []
    for path in _walk_python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED_PATHS:
            continue
        text = path.read_text(encoding="utf-8")
        for line_num, line in enumerate(text.splitlines(), start=1):
            for pattern in SHIM_PATTERNS:
                if pattern.search(line):
                    offenders.append(f"{rel}:{line_num}: {line.strip()}")

    assert not offenders, (
        "Backward-compat shim markers are forbidden in production code (ADR-0003). "
        "Delete the wrapper, move the helper to its canonical location, or update "
        "the comment if the marker is mislabelled. "
        f"Offenders ({len(offenders)}):\n  " + "\n  ".join(offenders)
    )
