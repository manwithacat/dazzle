# Format Layer Implementation Plan (#1470, format-layer slice)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make list/table grid cells render their declared type correctly by default (FK→name, money→currency, float→rounded, bool→Yes/No, enum→Title Case, datetime→friendly), retiring the raw-value leak class across every grid, with an optional inline `format:` field modifier for the cases type can't decide.

**Architecture:** Two phases. Phase 1 implements the existing `_format_cell` stub (`http/runtime/renderers/fragment_adapter.py`) by extracting a pure formatter into `render/fragment/format_cell.py` — no DSL change, fixes the leak class everywhere. Phase 2 adds an inline `field … format: kind[:arg]` modifier on surface fields (IR + parser + validation + page threading + a `dazzle inspect` hook).

**Tech Stack:** Python 3.12, Pydantic IR, pytest. No Jinja (typed-Fragment substrate). Layers: `http → page → render → core`.

## Global Constraints

- Layer rule: `render/` is pure (no I/O); `core/` must not import `page`/`http`; `page` must not import `http`. The pure formatter lives in `render/`; the http adapter calls it. (verbatim from repo import-linter contracts)
- `ruff check src/ tests/` and `ruff format src/ tests/` must pass; `mypy src/dazzle` must pass (bare command — matches /ship, /check, CI).
- Each phase gate must also pass `dazzle validate` on `examples/` and `pytest -m gate -q`.
- Column `type` string vocabulary (from `template_compiler._field_type_to_column_type`): `text`, `bool`, `date`, `currency`, `badge` (enum), `ref` (FK/belongs_to). `float`/`decimal`/`int`/`str` all map to `text` — so float rounding keys off the Python value type, not the column kind.
- Money columns: `_build_entity_columns` renames the key to `{field}_minor` (integer minor units) and sets `ColumnContext.currency_code`; currency formatting needs that code threaded to the formatter.
- FK columns: the read path already resolves the display value (`fk_display_only`), so a `ref` cell's value is already the name — `ref` formatting is just safe string/escaping, not a lookup.

---

## Phase 1 — Inference (no DSL change)

### Task 1: Pure `format_cell` formatter in `render/`

**Files:**
- Create: `src/dazzle/render/fragment/format_cell.py`
- Test: `tests/unit/render/fragment/test_format_cell.py`

**Interfaces:**
- Produces: `format_cell(value: Any, kind: str, *, currency_code: str = "", override: "ResolvedFormat | None" = None) -> str` and `ResolvedFormat` (a small frozen dataclass `kind: str`, `arg: str | None`). Phase 1 always passes `override=None`; the parameter exists so Phase 2 wires in without changing the signature. Returns an **HTML-escaped** string (routes through `dazzle.render.html.esc`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_format_cell.py
import datetime as dt
import pytest
from dazzle.render.fragment.format_cell import format_cell

@pytest.mark.parametrize("value,kind,kw,expected", [
    (None, "text", {}, ""),                       # None → blank
    (True, "bool", {}, "Yes"),
    (False, "bool", {}, "No"),
    ("ACTIVE", "badge", {}, "Active"),            # enum token → Title Case
    ("in_review", "badge", {}, "In Review"),
    (3.14159, "text", {}, "3.14"),                # float → 2dp (value-type keyed)
    (10.0, "text", {}, "10.00"),
    (42, "text", {}, "42"),                       # int → as-is
    ("Acme Ltd", "ref", {}, "Acme Ltd"),          # FK value already a name
    (12345, "currency", {"currency_code": "GBP"}, "£123.45"),  # minor units → currency
])
def test_inference(value, kind, kw, expected):
    assert format_cell(value, kind, **kw) == expected

def test_datetime_friendly():
    out = format_cell(dt.datetime(2026, 6, 24, 9, 30), "date", )
    assert "2026" in out and "ISO" not in out  # friendly, not raw isoformat

def test_escaping():
    assert format_cell("<script>", "text") == "&lt;script&gt;"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/render/fragment/test_format_cell.py -q`
Expected: FAIL (module `format_cell` does not exist).

- [ ] **Step 3: Implement the pure formatter**

```python
# src/dazzle/render/fragment/format_cell.py
"""Pure cell-value formatter for typed-table grids (#1470).

Renders a stored value to a display string by the column's declared kind
(plus the Python value type for numeric rounding). No I/O — unit-testable in
isolation. The http fragment adapter calls this; FK display values are already
resolved upstream, so `ref` is just safe stringification.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dazzle.render.html import esc


@dataclass(frozen=True)
class ResolvedFormat:
    kind: str
    arg: str | None = None


def _title_case(token: str) -> str:
    return token.replace("_", " ").replace("-", " ").strip().title()


def _currency(minor: Any, code: str) -> str:
    try:
        major = Decimal(int(minor)) / 100
    except (TypeError, ValueError):
        return esc(str(minor))
    symbol = {"GBP": "£", "USD": "$", "EUR": "€"}.get(code.upper(), "")
    return f"{symbol}{major:,.2f}" if symbol else f"{major:,.2f} {code}"


def _friendly_dt(value: Any, *, with_time: bool) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return esc(value)
    if isinstance(value, datetime):
        return value.strftime("%-d %b %Y %H:%M" if with_time else "%-d %b %Y")
    if isinstance(value, date):
        return value.strftime("%-d %b %Y")
    return esc(str(value))


def _infer(value: Any, kind: str, currency_code: str) -> str:
    if kind == "bool" or isinstance(value, bool):
        return "Yes" if value else "No"
    if kind == "currency":
        return _currency(value, currency_code or "GBP")
    if kind == "badge":
        return esc(_title_case(str(value)))
    if kind == "date":
        return esc(_friendly_dt(value, with_time=isinstance(value, datetime)))
    if isinstance(value, (float, Decimal)):
        return esc(f"{float(value):.2f}")
    return esc(str(value))


def format_cell(
    value: Any,
    kind: str,
    *,
    currency_code: str = "",
    override: ResolvedFormat | None = None,
) -> str:
    if value is None or value == "":
        return ""
    if override is not None:
        return _apply_override(value, override, currency_code)  # Phase 2
    return _infer(value, kind, currency_code)


def _apply_override(value: Any, fmt: ResolvedFormat, currency_code: str) -> str:
    # Phase 2 fills this in; Phase 1 never calls it (override is always None).
    raise NotImplementedError
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/render/fragment/test_format_cell.py -q`
Expected: PASS (10+ cases). Adjust the datetime strftime assertion if the platform lacks `%-d` (use `%d` fallback).

- [ ] **Step 5: Lint + type**

Run: `uv run ruff check src/dazzle/render/fragment/format_cell.py tests/unit/render/fragment/test_format_cell.py --fix && uv run ruff format src/dazzle/render/fragment/format_cell.py tests/unit/render/fragment/test_format_cell.py && uv run mypy src/dazzle`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/render/fragment/format_cell.py tests/unit/render/fragment/test_format_cell.py
git commit -m "feat(#1470): pure cell formatter (inference table) in render/"
```

### Task 2: Wire `_format_cell` to the helper + thread currency

**Files:**
- Modify: `src/dazzle/http/runtime/renderers/fragment_adapter.py` (`_format_cell` at ~line 644; the table-build call at ~line 122)
- Modify: `src/dazzle/page/converters/template_compiler.py` (ensure `currency_code` reaches the column dict the adapter consumes — confirm whether `ColumnContext.model_dump()` already carries it; if the adapter's column dicts drop it, add it)
- Test: `tests/unit/test_fragment_adapter_format.py`

**Interfaces:**
- Consumes: `format_cell` from Task 1.
- Produces: `_format_cell(value, kind, currency_code="")` delegates to `format_cell`. The per-row build passes `col.get("currency_code", "")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fragment_adapter_format.py
from dazzle.http.runtime.renderers.fragment_adapter import _format_cell

def test_adapter_delegates_to_formatter():
    assert _format_cell(True, "bool") == "Yes"
    assert _format_cell(12345, "currency", "GBP") == "£123.45"
    assert _format_cell(None, "text") == ""
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_fragment_adapter_format.py -q`
Expected: FAIL (`_format_cell` str-coerces — returns `"True"`, not `"Yes"`; signature has no currency arg).

- [ ] **Step 3: Implement**

Replace the stub body of `_format_cell` (fragment_adapter.py ~644) with a delegation:

```python
def _format_cell(value: Any, kind: str, currency_code: str = "") -> str:
    """Stringify a cell value for the typed Table via the pure formatter (#1470)."""
    from dazzle.render.fragment.format_cell import format_cell
    return format_cell(value, kind, currency_code=currency_code)
```

Update the per-row build (~line 122) to pass currency:

```python
_format_cell(item.get(col["key"]), col.get("type", "text"), col.get("currency_code", ""))
```

Then confirm the column dicts in `ctx["columns"]` carry `currency_code`. Read `template_compiler.py` where `ColumnContext` → dict (`_build_entity_columns` / `_build_surface_columns` callers / `.model_dump()`). If `currency_code` is present in the dumped dict, no change; if the column dicts are hand-built and omit it, add `"currency_code": col.currency_code`.

- [ ] **Step 4: Run to verify pass + no regression**

Run: `uv run pytest tests/unit/test_fragment_adapter_format.py tests/unit/render/fragment/ -q && uv run pytest tests/unit/test_table_empty_state_guard_1450.py tests/integration/test_examples_fragment_http.py -q`
Expected: PASS (the integration test renders real grids — cells now show Yes/No/currency/names, no exceptions).

- [ ] **Step 5: Lint + type + gate**

Run: `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/ && uv run mypy src/dazzle && uv run pytest -m gate -q`
Expected: all clean/green.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/renderers/fragment_adapter.py src/dazzle/page/converters/template_compiler.py tests/unit/test_fragment_adapter_format.py
git commit -m "feat(#1470): _format_cell delegates to the inference formatter + threads currency"
```

**Phase 1 gate (ship point):** `uv run ruff check src/ tests/ && uv run mypy src/dazzle && uv run pytest -m gate -q && uv run pytest tests/integration/test_examples_fragment_http.py -q` all green. At this point the leak class is fixed app-wide with no DSL change — a valid release (`/bump patch`, ship).

---

## Phase 2 — Inline `format:` override modifier

### Task 3: `FieldFormatSpec` IR + surface-field `format` attribute

**Files:**
- Modify: the surface-field IR model (the model constructed in `core/dsl_parser_impl/surface.py` `_parse_field` ~line 468; find its class in `core/ir/` — likely `surfaces.py`). Add `format: FieldFormatSpec | None = None`.
- Create/Modify: `FieldFormatSpec` Pydantic model (`kind: str`, `arg: str | None = None`) in the same IR module.
- Test: `tests/unit/test_field_format_ir.py`

- [ ] **Step 1:** Write a test constructing the surface-field model with `format=FieldFormatSpec(kind="currency", arg="GBP")` and asserting round-trip + default `None`.
- [ ] **Step 2:** Run → fail (attribute/model missing).
- [ ] **Step 3:** Add `FieldFormatSpec` + the `format` attribute (default `None`, so all existing constructions are unaffected).
- [ ] **Step 4:** Run → pass.
- [ ] **Step 5:** `uv run mypy src/dazzle` + ruff.
- [ ] **Step 6:** Commit `feat(#1470): FieldFormatSpec IR + surface-field format attribute`.

### Task 4: Parse the `format:` trailing modifier

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/surface.py` (`_parse_field_trailing_modifiers` ~line 499; it already handles `visible:`/`when:`/`help:`/`key=value`).
- Test: `tests/unit/test_parser.py` (or a focused `tests/unit/test_surface_format_modifier.py`).

**Interfaces:** Consumes `FieldFormatSpec` (Task 3). Produces: a parsed `format` on the field model; helper `_parse_format_spec(raw: str) -> FieldFormatSpec` splitting `kind[:arg]`.

- [ ] **Step 1:** Failing test — parse `field amount "Amount" format: currency:GBP` → field `.format == FieldFormatSpec("currency", "GBP")`; `format: percent` → arg `None`; a field with no modifier → `.format is None`; existing `visible:`/`help:` still parse.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Add `format` to the trailing-modifier dispatch; split on the first `:` after the kind for the arg.
- [ ] **Step 4:** Run → pass; run the full parser suite `uv run pytest tests/unit/test_parser.py -q`.
- [ ] **Step 5:** ruff + mypy.
- [ ] **Step 6:** Commit `feat(#1470): parse field format: trailing modifier`.

### Task 5: Validation — `E_FORMAT_*` kind + kind/type compatibility

**Files:**
- Modify: the surface/field validation pass in `core/validation/` (find the validator that walks surface fields; grep `E_` codes there for the pattern).
- Test: `tests/unit/test_format_validation.py`

**Interfaces:** the v1 vocabulary set `{currency, percent, round, date, datetime, relative, title_case, upper, lower, yes_no, display_name, raw}` and a kind→allowed-FieldTypeKind compatibility map.

- [ ] **Step 1:** Failing tests — `format: bogus` → `E_FORMAT_UNKNOWN_KIND`; `format: currency` on a `str` field → `E_FORMAT_TYPE_MISMATCH`; `format: display_name` on a non-FK → error; a valid `currency:GBP` on a money/float field → no error.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Implement the validator: unknown kind, then kind/type compatibility (currency/round/percent ⇒ money/float/int/decimal; display_name ⇒ ref/belongs_to; date/datetime/relative ⇒ date/datetime; case/yes_no/raw ⇒ any).
- [ ] **Step 4:** Run → pass; run `uv run pytest -m gate -q` (drift gates may need a new error-code registration — follow the existing E_-code pattern).
- [ ] **Step 5:** ruff + mypy.
- [ ] **Step 6:** Commit `feat(#1470): validate field format kind + kind/type compatibility`.

### Task 6: Thread the override through to the formatter

**Files:**
- Modify: `template_compiler.py` `_build_surface_columns` — copy the surface field's `format` into `ColumnContext` (add `format_kind: str = ""`, `format_arg: str = ""` to `ColumnContext` in `render/context.py`) and into the column dict.
- Modify: `fragment_adapter.py` `_format_cell` signature → `(value, kind, currency_code="", format_kind="", format_arg=None)`; build a `ResolvedFormat` when `format_kind` is set and pass `override=` to `format_cell`.
- Modify: `render/fragment/format_cell.py` — implement `_apply_override` (the kinds; override wins over inference).
- Test: extend `tests/unit/render/fragment/test_format_cell.py` + `test_fragment_adapter_format.py`.

- [ ] **Step 1:** Failing tests — `format_cell(0.5, "text", override=ResolvedFormat("percent","1"))=="50.0%"`; `format_cell(1234.5, "text", override=ResolvedFormat("round","0"))=="1,234"` — wait, define precisely: `round:0`→`"1235"`; `ResolvedFormat("upper")` on `"hi"`→`"HI"`; `ResolvedFormat("raw")` returns the escaped raw value; override beats the inferred kind.
- [ ] **Step 2:** Run → fail (`_apply_override` raises `NotImplementedError`).
- [ ] **Step 3:** Implement `_apply_override` for each vocabulary kind; thread `ColumnContext.format_*` → column dict → `_format_cell` → `format_cell(override=...)`.
- [ ] **Step 4:** Run → pass; integration render test still green.
- [ ] **Step 5:** ruff + mypy + `pytest -m gate -q`.
- [ ] **Step 6:** Commit `feat(#1470): thread field format override to the formatter (override wins)`.

### Task 7: `dazzle inspect` resolved-format hook

**Files:**
- Modify: the `dazzle inspect` CLI (`cli/` inspect command — grep `inspect` subcommands) to add a `resolved-formats <surface>` view printing each field → `{explicit|inferred} kind[:arg]`.
- Test: `tests/unit/test_inspect_resolved_formats.py`

- [ ] **Step 1:** Failing test — for a surface with one `format:` field + one inferred, the inspect output lists both with the right source label.
- [ ] **Step 2–4:** Implement (reuse `resolve_format` logic — extract the inference resolution into a shared pure function `resolve_format(field_type, override) -> ResolvedFormat` in `format_cell.py` if not already, so inspect and the formatter agree); run → pass.
- [ ] **Step 5:** ruff + mypy.
- [ ] **Step 6:** Commit `feat(#1470): dazzle inspect resolved-formats traceability hook`.

### Task 8: Example-app demonstration + fidelity check

**Files:**
- Modify: one example app's list surface (e.g. `examples/acme_billing` or `invoice_ops`) to add `format:` modifiers on an amount/rate/date field.
- Test: a fidelity/render assertion (extend `tests/integration/test_examples_fragment_http.py` or the example's existing render test) that the rendered cells show formatted values.

- [ ] **Step 1:** Add `format: currency:GBP` / `percent:N` / `date:short` to a real list surface; `dazzle validate` that example.
- [ ] **Step 2:** Failing/▢ render test asserting the cell HTML contains the formatted string (e.g. `£`, not the raw minor-units integer).
- [ ] **Step 3:** Confirm it passes end-to-end.
- [ ] **Step 4:** Run `uv run dazzle validate` in the example + the integration test.
- [ ] **Step 5:** ruff + mypy + `pytest -m gate -q`.
- [ ] **Step 6:** Commit `feat(#1470): demonstrate field format: in <example> + fidelity check`. Update CHANGELOG + docs/reference/reports.md (or a new docs/reference/field-format.md) noting the `format:` modifier + inference table. `/bump` + ship.

---

## Self-review

- **Spec coverage:** inference table → Task 1; `_format_cell` integration + currency → Task 2; grammar/IR → Task 3; parser → Task 4; validation → Task 5; threading/override → Task 6; traceability hook → Task 7; example + docs → Task 8. All spec sections covered.
- **Type consistency:** `format_cell(value, kind, *, currency_code="", override=None)` and `ResolvedFormat(kind, arg)` are introduced in Task 1 and used unchanged in Tasks 2/6/7. `_format_cell` grows `currency_code` (Task 2) then `format_kind/format_arg` (Task 6) — signature evolution is stated in each task. `ColumnContext` gains `format_kind`/`format_arg` in Task 6.
- **Known unknowns flagged for the implementer (read-first, not fabricated):** the exact surface-field IR class name (Task 3 — constructed at surface.py ~468), whether `currency_code` already survives into the adapter column dict (Task 2 Step 3), and the surface-field validation pass location (Task 5). Each task says where to look and the contract to satisfy.
- **Placeholder scan:** `_apply_override` is intentionally `NotImplementedError` in Phase 1 (never called there) and implemented in Task 6 — stated, not a gap.

## Notes

- **Float rounding keys off the Python value type**, not the column kind (the column vocabulary collapses float/decimal/int to `text`). The `int`-vs-`float` distinction is therefore value-driven: `42`→`"42"`, `42.0`→`"42.00"`.
- Phase 1 is independently shippable and delivers the leak-class fix; Phase 2 is purely additive (default `None`/`""`, so unannotated apps are unchanged).
