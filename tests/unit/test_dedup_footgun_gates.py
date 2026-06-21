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
        "`dazzle.http.runtime.http_errors.require_found(value)` instead:\n  " + "\n  ".join(hits)
    )


def test_no_inline_identity_fallback() -> None:
    """`getattr(x,"name",None) or getattr(x,"id",...)` → `spec_display_id(x)`.

    Both orderings are gated (#1442): name-first → `spec_display_id(x)`, and the
    id-first PersonaSpec orientation → `spec_display_id(x, prefer="id")`.
    """
    pat = re.compile(
        r'getattr\(\w+, "name", None\) or getattr\(\w+, "id"'  # name-first
        r'|getattr\(\w+, "id", None\) or getattr\(\w+, "name"'  # id-first (#1442)
    )
    hits = [
        str(p.relative_to(_SRC.parent.parent))
        for p in _src_files({"identity.py"})
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not hits, (
        "Inline name/id identity fallback found — use "
        '`dazzle.core.ir.identity.spec_display_id(spec)` (add `prefer="id"` for the '
        "PersonaSpec id-first order) instead:\n  " + "\n  ".join(hits)
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


def test_region_builders_use_typed_context() -> None:
    """Region builders take `ctx: RegionContext`, not `ctx: dict[str, Any]`.

    The Fragment substrate (ADR-0023) is typed; the region-builder context was the last
    `dict[str, Any]` hole. `RegionContext` (render/fragment/region/_context.py) documents
    the ~91 keys the `_build_*` methods read. Re-introducing `ctx: dict[str, Any]` in a
    builder drops back to the untyped bag.
    """
    region_dir = _SRC / "render" / "fragment" / "region"
    hits = [
        f"{p.relative_to(_SRC.parent.parent)}"
        for p in region_dir.glob("_builders_*.py")
        if "ctx: dict[str, Any]" in p.read_text(encoding="utf-8")
    ]
    assert not hits, (
        "Region builder(s) still take `ctx: dict[str, Any]` — use `ctx: RegionContext` "
        "(dazzle.render.fragment.region._context):\n  " + "\n  ".join(hits)
    )
