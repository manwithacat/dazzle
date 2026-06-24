# Insight region primitives — design spec (#1470)

**Status:** approved (brainstorm), ready for implementation plan
**Date:** 2026-06-24
**Issue:** #1470
**Scope of this spec:** build-ready design for the **per-field `format:` layer** (the first slice); sequenced roadmap for the remaining net-new primitives (`display: comparison`, `outlier`/`rag` decorator, `insight_summary`). Each later primitive gets its own spec when its turn comes.

## Background

#1470 proposed a basket of "insight" region primitives. Investigation found Dazzle's region vocabulary is far richer than the RFC assumed — ~45 `DisplayMode` values already ship, including `heatmap`, `sparkline`, `line_chart`/`area_chart` with target bands (`ReferenceBand`), `bullet`, `bar_track`, and metric delta badges (`DeltaSpec`). So most proposed Tier-1 viz primitives already exist (at most they want a docs alias).

The genuinely net-new, high-leverage work is narrow:

1. **Per-field `format:` layer** — table/list `fields:` are a bare `list[str]` today, so cells render raw: FK UUIDs instead of names, unrounded floats, raw `True`/`False`, SCREAMING_ENUM tokens. This is a leak *class* across every grid.
2. **`display: comparison`** — a named ranked-league mode with an automatic outlier flag.
3. **`outlier`/`rag` cell decorator** — generalise chart thresholds into a per-cell table decorator.
4. **`insight_summary`** — an LLM narrative header (its own ADR-worthy effort).

This spec designs (1) in full and sequences (2)–(4).

## Goals / non-goals

**Goals**
- Make *correct* cell formatting the default for every list/table region, derived from the field's declared type — retire the UUID/float/bool/enum leak class app-wide with zero author effort.
- Provide a sparse, non-breaking `format:` override for what type can't decide (currency, percent, date granularity, etc.).
- Keep the construct pure presentation: no change to queries, scope, RBAC, or the data-fetch path.

**Non-goals (v1)**
- Custom strftime/printf format strings; full i18n number/currency localization; per-locale currency placement.
- The other three primitives (designed later).
- Any change to chart/aggregate regions (they already format via their own config).

## Format layer — design

### Grammar

Region blocks gain one optional key, `format:`, a **sparse** map of `field → format-spec`. `fields: [...]` is unchanged (fully backward-compatible — existing regions keep working untouched). A format-spec is a bare kind or `kind:arg`.

```
region revenue "Revenue":
  mode: list
  source: Invoice
  fields: [customer, amount, rate, status, created]
  format:
    amount: currency:GBP
    rate: percent:1
    created: date:short
  # customer → display-name, status → title-case, etc. are INFERRED (no entry)
```

### Inference table

Applied to every displayed field that has **no** `format:` entry. This is what retires the leak class:

| Declared type        | Inferred render                                        |
|----------------------|-------------------------------------------------------|
| FK / `ref`           | the target's display field (name), never the UUID     |
| `money`              | currency, using the money field's own currency        |
| `float`              | rounded (default 2 dp)                                 |
| `bool`               | `Yes` / `No`                                           |
| `enum`               | Title Case of the token                                |
| `datetime`           | friendly datetime (`date` → friendly date)            |
| `uuid` (non-FK), `int`, `str` | as-is (HTML-escaped)                         |

FK → display-name is already resolved in the region read path (`workspace_region_fetch.py` `fk_display_only=True`, `workspace_region_render.py` `display_field`), so the format layer formalises it alongside the other types without touching the fetch.

### Override vocabulary (v1, YAGNI-bounded)

`currency[:CODE]`, `percent[:dp]`, `round:dp`, `date:short|long|iso`, `datetime:short|long|relative`, `relative`, `title_case`, `upper`, `lower`, `yes_no`, `display_name`, and `raw` (escape hatch — show the stored value verbatim, e.g. to expose a UUID deliberately).

### Precedence

explicit `format:` entry > type inference > raw. An unknown kind, or a kind/type mismatch (e.g. `currency` on a `str`), is a **validation error** (fail-loud), not a silent fallback.

## Architecture & placement (`http → page → render → core`)

- **Core — IR + parser.** `WorkspaceRegion` gains `field_formats: dict[str, FieldFormatSpec]`, where `FieldFormatSpec(kind: str, arg: str | None)`. The region-block parser (`src/dazzle/core/dsl_parser_impl/workspace.py`) adds `format` to the block's `valid_keys` and parses the indented `field: kind[:arg]` map. `fields:` parsing is untouched.
- **Core — validation.** A validator pass: each `format:` key must name a field present in the region / its `source` entity; `kind` must be in the v1 vocabulary; `kind`/type must be compatible (`currency`/`round`/`percent` ⇒ money/float/int; `display_name` ⇒ FK; `date`/`datetime`/`relative` ⇒ date/datetime; etc.). Violations are `E_FORMAT_*` errors surfaced at `dazzle validate`.
- **Render — pure, no I/O.** Two pure functions:
  - `resolve_format(field_type, override) → ResolvedFormat` — combines the inference table with the override (override wins).
  - `format_cell(value, resolved) → str` — value → escaped string; handles `None` (→ blank/em-dash) and routes through the existing `render.html.esc`.

  Applied in the list/table cell render pass (`src/dazzle/render/fragment/region/_builders_tables.py` plus the list builder), over rows whose FK display values are already resolved upstream.

This keeps formatting logic pure and unit-testable in isolation (field-type + value + spec → string); IR/parser/validation live in core; nothing touches the data-fetch or scope path.

### Traceability hook

A small `dazzle inspect`/explain addition prints the **resolved** format per region field (explicit-vs-inferred + kind/arg), so an engineer can trace any rendered cell back to its DSL/AppSpec origin.

## Model-driven failure-modes check (new DSL construct)

1. **Risk:** "hidden/magic semantics" — inference could obscure what a cell shows.
2. **Detector:** `dazzle validate` (`E_FORMAT_*` + kind/type compatibility); the inference is a pure function of the field's declared type + any explicit override.
3. **Live?** Yes — `validate` runs in `dazzle lint` and CI.
4. **Traceable?** Yes — a field's format is its explicit `format:` entry or derived from its AppSpec type; nothing request-time or stateful. The `inspect`/explain hook surfaces the resolved format.
5. **Semantics preserved?** Yes — pure presentation **after** the scope-safe fetch; no change to queries, scope, RBAC, or the data path. No security surface.

→ Low residual risk: presentation-only, schema-derived, validated, traceable. Safe to document as a pattern once shipped.

## Testing (format layer)

Pure unit tests — no Postgres:
- `resolve_format`: every declared type → its inferred kind; override beats inference.
- `format_cell`: every override kind, plus `None` handling and HTML escaping (no double-escape, no injection).
- Parser: the `format:` block parses to `field_formats`; `kind:arg` splits correctly; `fields:`-only regions still parse unchanged.
- Validation: each `E_FORMAT_*` case (unknown field, unknown kind, kind/type mismatch).
- One example-app region using `format:` as a render/fidelity check (the rendered cells show names/rounded/Yes-No/currency, not raw values).

## Roadmap — the other three primitives (sketch only; each its own spec)

- **`display: comparison`** (ranked league + auto-outlier): new `DisplayMode` value + a thin builder over the existing `Repository.aggregate` GROUP BY, plus a ranking/outlier pass (IQR or σ flag). Renders cells through the format layer. Composes with no new fetch machinery.
- **`outlier`/`rag` cell decorator:** generalise the existing chart thresholds (`ReferenceBand`/`tone_bands`) into a per-cell table decorator. Orthogonal to value formatting (decoration vs value), composes cleanly. Pairs naturally with `comparison`.
- **`insight_summary`:** an LLM narrative header. Deferred behind its **own ADR** (LLM call + citation/scope/confidence + trust UX) — it is the only item that introduces a dependency.

**Build sequence:** ① format layer (this spec → plan → build) → ② comparison + outlier decorator (paired) → ③ insight_summary (ADR-gated).

## Out of scope (RFC items that are not region primitives)

Command palette, saved views, bulk toolbar, detail drawer, density toggle — these are app-shell / UX features, not region primitives, and are out of scope for #1470's core.
