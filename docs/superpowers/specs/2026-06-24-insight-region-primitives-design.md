# Insight region primitives — design spec (#1470)

**Status:** approved (brainstorm), ready for implementation plan
**Date:** 2026-06-24
**Issue:** #1470
**Scope of this spec:** build-ready design for the **per-field `format:` layer** (the first slice); sequenced roadmap for the remaining net-new primitives (`display: comparison`, `outlier`/`rag` decorator, `insight_summary`). Each later primitive gets its own spec when its turn comes.

> **Revision (post-investigation):** the architecture and override grammar below were corrected after tracing the real cell-render path. The *design* (inference-first + override, leak-class fix, validation, traceability) is unchanged; the integration points and override syntax now reflect the actual code: the existing `_format_cell` stub + an inline surface-field modifier (not a new `WorkspaceRegion` field + sibling map).

## Background

#1470 proposed a basket of "insight" region primitives. Investigation found Dazzle's region vocabulary is far richer than the RFC assumed — ~45 `DisplayMode` values already ship, including `heatmap`, `sparkline`, `line_chart`/`area_chart` with target bands (`ReferenceBand`), `bullet`, `bar_track`, and metric delta badges (`DeltaSpec`). So most proposed Tier-1 viz primitives already exist (at most they want a docs alias).

The genuinely net-new, high-leverage work is narrow:

1. **Per-field `format:` layer** — list/table cells render raw today: FK UUIDs instead of names, unrounded floats, raw `True`/`False`, SCREAMING_ENUM tokens. The cell stringifier `_format_cell` (`http/runtime/renderers/fragment_adapter.py`) is an explicit stub — its docstring says "Plan 6 or later adds badge/bool/date/currency/ref support"; today it `str()`-coerces everything. This is a leak *class* across every grid.
2. **`display: comparison`** — a named ranked-league mode with an automatic outlier flag.
3. **`outlier`/`rag` cell decorator** — generalise chart thresholds into a per-cell table decorator.
4. **`insight_summary`** — an LLM narrative header (its own ADR-worthy effort).

This spec designs (1) in full and sequences (2)–(4).

## Goals / non-goals

**Goals**
- Make *correct* cell formatting the default for every list/table grid, derived from the field's declared type — retire the UUID/float/bool/enum leak class app-wide with zero author effort.
- Provide an optional inline `format:` override for what type can't decide (currency code, percent precision, date granularity, etc.).
- Keep the construct pure presentation: no change to queries, scope, RBAC, or the data-fetch path.

**Non-goals (v1)**
- Custom strftime/printf format strings; full i18n number/currency localization; per-locale currency placement.
- The other three primitives (designed later).
- A sibling `format:` map for bracketed `fields: [...]` regions (`EntityCardSection`) — the inference half already formats those grids correctly; an explicit override there is a later add if needed.
- Any change to chart/aggregate regions (they already format via their own config).

## Format layer — design

The layer has two halves that ship in sequence:

- **Inference (Phase 1, no DSL change):** correct formatting derived from each field's declared type. Fixes the leak class across every grid on its own.
- **Override (Phase 2, inline modifier):** an explicit per-field `format:` for what type can't decide.

### Inference table

`_format_cell(value, kind)` renders by the column's declared type. The column `type` (and, for money, the currency) already flow from `_build_entity_columns` / `_build_surface_columns` (`page/converters/template_compiler.py`), which already special-cases `MONEY` (carries `currency_code`) and `REF`/`BELONGS_TO` (resolves to the display key). Inference fills in the rest:

| Declared type (`FieldTypeKind`) | Inferred render |
|---|---|
| `REF` / `BELONGS_TO` | the target's display field (name); the read path already resolves it (`fk_display_only`), so the value is already the name |
| `MONEY` | currency, using the column's `currency_code` |
| `float` | rounded (default 2 dp) |
| `bool` | `Yes` / `No` |
| `enum` | Title Case of the token |
| `datetime` | friendly datetime (`date` → friendly date) |
| `uuid` (non-FK), `int`, `str` | as-is (HTML-escaped) |
| `None` value (any type) | empty string |

### Grammar (Phase 2 override)

The main grids are **list surfaces**, whose fields are declared as `field <name> "<label>"` lines that already accept **trailing modifiers** (`visible:` / `when:` / `help:` / `key=value`, mixed-order — see `_parse_field_trailing_modifiers`). The override is a new trailing modifier, `format:`, mirroring that established pattern (NOT a sibling map — surfaces don't use bracketed `fields:` lists). A format-spec is a bare kind or `kind:arg`.

```
surface invoices "Invoices":
  uses entity Invoice
  mode: list
  section main:
    field amount "Amount" format: currency:GBP
    field rate "Rate" format: percent:1
    field status "Status"          # enum → Title Case (inferred)
    field customer "Customer"      # FK → display name (inferred)
    field created "Created"        # datetime → friendly (inferred)
```

### Override vocabulary (v1, YAGNI-bounded)

`currency[:CODE]`, `percent[:dp]`, `round:dp`, `date:short|long|iso`, `datetime:short|long|relative`, `relative`, `title_case`, `upper`, `lower`, `yes_no`, `display_name`, and `raw` (escape hatch — show the stored value verbatim, e.g. to expose a UUID deliberately).

### Precedence

explicit `format:` modifier > type inference > raw. An unknown kind, or a kind/type mismatch (e.g. `currency` on a `str`), is a **validation error** (fail-loud), not a silent fallback.

## Architecture & placement (`http → page → render → core`)

**Phase 1 — inference (no DSL change):**
- **`_format_cell(value, kind, currency=None)`** in `src/dazzle/http/runtime/renderers/fragment_adapter.py` — replace the str-coerce stub with the inference table. Pure function. The formatting *logic* is extracted into a pure helper in `src/dazzle/render/` (`render/fragment/format_cell.py`) so it is unit-testable with no I/O and reusable; `_format_cell` becomes a thin call into it. Callers already pass `col.get("type")`; the money currency is added to the column dict from the existing `ColumnContext` currency.

**Phase 2 — override:**
- **Core — IR.** The surface field model (`SurfaceField` in `core/ir`) gains `format: FieldFormatSpec | None`, where `FieldFormatSpec(kind: str, arg: str | None)`.
- **Core — parser.** `_parse_field_trailing_modifiers` (`core/dsl_parser_impl/surface.py`) accepts `format:` and parses the `kind[:arg]` value into `FieldFormatSpec`.
- **Core — validation.** A validator pass: `kind` must be in the v1 vocabulary; `kind`/type must be compatible (`currency`/`round`/`percent` ⇒ money/float/int; `display_name` ⇒ FK; `date`/`datetime`/`relative` ⇒ date/datetime). Violations are `E_FORMAT_*` errors at `dazzle validate`.
- **Page — threading.** `_build_surface_columns` (`page/converters/template_compiler.py`) copies the field's `format` into the `ColumnContext` and thence the column dict, so `_format_cell(value, kind, currency, fmt)` receives the override. Override wins over inference.

This keeps the formatting logic pure and unit-testable in isolation (type + value + spec → string); IR/parser/validation in core; threading in page; the formatter callable from the http adapter. No change to the data-fetch or scope path.

### Traceability hook

A small `dazzle inspect` addition prints the **resolved** format per surface-list field (explicit-vs-inferred + kind/arg), so an engineer can trace any rendered cell back to its DSL/AppSpec origin. (Phase 2.)

## Model-driven failure-modes check (new DSL construct)

1. **Risk:** "hidden/magic semantics" — inference could obscure what a cell shows.
2. **Detector:** `dazzle validate` (`E_FORMAT_*` + kind/type compatibility); the inference is a pure function of the field's declared type + any explicit override.
3. **Live?** Yes — `validate` runs in `dazzle lint` and CI.
4. **Traceable?** Yes — a field's format is its explicit `format:` modifier or derived from its AppSpec type; nothing request-time or stateful. The `inspect` hook surfaces the resolved format.
5. **Semantics preserved?** Yes — pure presentation **after** the scope-safe fetch; no change to queries, scope, RBAC, or the data path. No security surface.

→ Low residual risk: presentation-only, schema-derived, validated, traceable. Safe to document as a pattern once shipped.

## Testing

Pure unit tests — no Postgres:
- **Phase 1:** `render/fragment/format_cell.py` — every `FieldTypeKind` → its inferred rendering (`bool`→Yes/No, `float`→2dp, `enum`→Title Case, `datetime`→friendly, `money`→currency with code, `None`→""); HTML escaping (no double-escape, no injection). Plus an adapter-level test that `_format_cell` routes through it.
- **Phase 2:** parser — `field x "X" format: currency:GBP` parses to `FieldFormatSpec(kind="currency", arg="GBP")`; `kind:arg` splits; a field with no `format:` is `None`. Validation — each `E_FORMAT_*` case (unknown kind, kind/type mismatch). Threading — `_build_surface_columns` carries `format` into the column dict; override beats inference in `_format_cell`.
- One example-app list surface using `format:` as a render/fidelity check (cells show names/rounded/Yes-No/currency, not raw values).

## Build sequence (this spec)

1. **Phase 1 — inference** (`_format_cell` + extracted pure helper). No DSL change; fixes the leak class across every grid. Ships the bulk of the value alone.
2. **Phase 2 — override** (`format:` field modifier: IR + parser + validation + page threading + `inspect` hook).

## Roadmap — the other three primitives (sketch only; each its own spec)

- **`display: comparison`** (ranked league + auto-outlier): new `DisplayMode` value + a thin builder over the existing `Repository.aggregate` GROUP BY, plus a ranking/outlier pass (IQR or σ flag). Renders cells through the format layer.
- **`outlier`/`rag` cell decorator:** generalise the existing chart thresholds (`ReferenceBand`/`tone_bands`) into a per-cell table decorator. Orthogonal to value formatting; composes cleanly. Pairs with `comparison`.
- **`insight_summary`:** an LLM narrative header. Deferred behind its **own ADR** (LLM call + citation/scope/confidence + trust UX) — the only item that introduces a dependency.

**Overall build order:** format layer (this spec) → comparison + outlier decorator (paired) → insight_summary (ADR-gated).

## Out of scope (RFC items that are not region primitives)

Command palette, saved views, bulk toolbar, detail drawer, density toggle — these are app-shell / UX features, not region primitives, and are out of scope for #1470's core.
