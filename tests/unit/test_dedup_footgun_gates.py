"""Gates that keep three deduplicated footgun classes from creeping back (smells round 2026-06-19).

Each pattern was retired into a shared helper; these gates forbid the inline form from
reappearing so the next copy-paste fails CI with a pointer to the helper. The helper-
definition files are excluded (they legitimately contain the pattern body).
"""

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "dazzle"


def _src_files(exclude: set[str]) -> list[Path]:
    return [p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts and p.name not in exclude]


def test_no_inline_404_guard() -> None:
    """`if x is None: raise HTTPException(404, "Not found")` → `require_found(x)`."""
    pat = re.compile(
        r'if \w+ is None:\s*\n\s*raise HTTPException\(status_code=404, detail="Not found"\)'
    )
    hits = [
        str(p.relative_to(_SRC.parent.parent))
        for p in _src_files({"http_errors.py"})
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not hits, (
        "Inline fetch-or-404 guard found — use "
        "`dazzle.back.runtime.http_errors.require_found(value)` instead:\n  " + "\n  ".join(hits)
    )


def test_no_inline_identity_fallback() -> None:
    """`getattr(x,"name",None) or getattr(x,"id",...)` → `spec_display_id(x)`."""
    pat = re.compile(r'getattr\(\w+, "name", None\) or getattr\(\w+, "id"')
    hits = [
        str(p.relative_to(_SRC.parent.parent))
        for p in _src_files({"identity.py"})
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not hits, (
        "Inline name/id identity fallback found — use "
        "`dazzle.core.ir.identity.spec_display_id(spec)` instead:\n  " + "\n  ".join(hits)
    )


def test_no_inline_state_normalisation() -> None:
    """`s if isinstance(s, str) else s.name` → `StateMachineSpec.state_names()` / `state_name(s)`."""
    pat = re.compile(r"isinstance\([\w.]+, str\) else [\w.]+\.name")
    hits = [
        str(p.relative_to(_SRC.parent.parent))
        for p in _src_files({"state_machine.py"})
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not hits, (
        "Inline state-name normalisation found — use "
        "`StateMachineSpec.state_names()` or `dazzle.core.ir.state_machine.state_name(s)`:\n  "
        + "\n  ".join(hits)
    )
