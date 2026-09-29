"""Gates that keep deduplicated footgun classes from creeping back (smells round 2026-06-19).

Each pattern was retired into a shared helper; these gates forbid the inline form from
reappearing so the next copy-paste fails CI with a pointer to the helper. The helper-
definition files are excluded (they legitimately contain the pattern body).
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_SRC = Path(__file__).resolve().parents[2] / "src" / "dazzle"


def _src_files(exclude: set[str]) -> list[Path]:
    return [p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts and p.name not in exclude]


def test_no_inline_entity_slug() -> None:
    """`<name>.lower().replace("_", "-")` → `dazzle.core.strings.entity_slug(name)` (#1440).

    The canonical slug formula lives in ``core.strings`` (re-exported by
    ``page.app_paths`` as the #1426 link entry point). Re-deriving it inline lets the
    registration↔link slug rule drift — the #1421/#1426 dead-link footgun class.
    """
    pat = re.compile(r"""lower\(\)\.replace\((['"])_\1, (['"])-\2\)""")
    hits = [
        str(p.relative_to(_SRC.parent.parent))
        for p in _src_files({"strings.py", "app_paths.py"})
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not hits, (
        "Inline entity-slug formula found — use "
        "`dazzle.core.strings.entity_slug(name)` (or `dazzle.page.app_paths.entity_slug`, "
        "or the `app_paths.*_path` builders for full /app URLs):\n  " + "\n  ".join(hits)
    )


def test_no_inline_404_guard() -> None:
    """`if x is None: raise HTTPException(404, …)` → `require_found(x, …)` (#1441).

    Matches the fetch-or-404 None-guard shape with ANY detail (custom message or a
    dict) and either the keyword (`status_code=404`) or positional (`404, …`) form —
    so domain-specific messages no longer sidestep the gate. Other 404 raises (membership
    / path-exists / dict-lookup checks) are NOT None-guards and are intentionally
    out of scope.
    """
    pat = re.compile(r"if \w+ is None:\s*\n\s*raise HTTPException\(\s*(?:status_code=)?404\b")
    hits = [
        str(p.relative_to(_SRC.parent.parent))
        for p in _src_files({"http_errors.py"})
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not hits, (
        "Inline fetch-or-404 guard found — use "
        "`dazzle.http.runtime.http_errors.require_found(value)` instead:\n  " + "\n  ".join(hits)
    )


def test_logger_uses_dunder_name_not_string_bucket() -> None:
    """`getLogger("dazzle.<...>")` → `getLogger(__name__)` (#1435).

    A hand-written dotted logger name (`getLogger("dazzle.server")`) is a silent
    footgun: it re-parents records under a shared bucket, so a module rename orphans
    them and per-module level filtering breaks. Every module logger must derive from
    `__name__`. Intentional shared channels are allowed only via a *named constant*
    (the literal `getLogger("dazzle.x")` form is what's forbidden), and the framework
    root logger (`getLogger("dazzle")`, no dot — configured in `log_setup.py` /
    `http/runtime/logging.py`) plus third-party library loggers (e.g. `pygls`) are
    fine since they don't match the dotted-`dazzle.` literal.
    """
    pat = re.compile(r"""getLogger\(['\"]dazzle\.""")
    hits = [
        str(p.relative_to(_SRC.parent.parent))
        for p in _src_files(set())
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not hits, (
        'Logger acquired by a literal `getLogger("dazzle.<...>")` bucket name — use '
        "`logging.getLogger(__name__)` (or a named constant for a deliberate shared "
        "channel):\n  " + "\n  ".join(hits)
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


# Inlined minor-unit divisors. Deliberately excludes 1000: ISO-4217 scale 3
# would inline as 1000, but so does a K/M/B magnitude abbreviation
# (pitch/_fmt_currency), so 1000 cannot be distinguished by shape. That case is
# covered by the authoritative output check in test_money_scale_parity.py — this
# gate is best-effort prevention for the unambiguous literals.
_MINOR_UNIT_DIVISORS = {2, 10, 100}
_CURRENCY_NAME = re.compile(r"(currency|money|minor|amount)", re.IGNORECASE)


def _divides_minor_units_by_literal(path: Path) -> list[int]:
    """Line numbers where a currency-ish function divides by a power-of-ten literal."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _CURRENCY_NAME.search(node.name):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.BinOp)
                and isinstance(inner.op, ast.Div)
                and isinstance(inner.right, ast.Constant)
                and isinstance(inner.right.value, int)
                and inner.right.value in _MINOR_UNIT_DIVISORS
            ):
                found.append(inner.lineno)
    return found


def test_no_inline_currency_minor_unit_scale() -> None:
    """`Decimal(x) / 100` in a currency helper → `get_currency_scale(code)`.

    ``format_cell._currency`` divided minor units by a hardcoded 100 and formatted
    with a fixed ``,.2f``, so a JPY amount rendered 100x too small while
    ``render/filters._currency_filter`` (which honours the table) rendered it
    correctly — the same record disagreed between surfaces and CSV export.

    The canonical scale table is ``dazzle.core.ir.money.CURRENCY_SCALES``, read
    via ``get_currency_scale(code)``. This gate covers the unambiguous literals;
    ``test_money_scale_parity.py`` is the authoritative check because it asserts
    the rendered magnitude regardless of how the divisor was written.
    """
    hits: list[str] = []
    for path in _src_files({"money.py", "money_migration.py"}):
        for lineno in _divides_minor_units_by_literal(path):
            hits.append(f"{path.relative_to(_SRC.parent.parent)}:{lineno}")
    assert not hits, (
        "Inline minor-unit currency divisor found — divide by "
        "`10 ** get_currency_scale(code)` (dazzle.core.ir.money) and take the format "
        "precision from the same table, or use `_currency_filter`:\n  " + "\n  ".join(hits)
    )
