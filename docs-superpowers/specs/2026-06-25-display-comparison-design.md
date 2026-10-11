# `display: comparison` — ranked-league region primitive — design spec (#1470)

**Status:** approved (brainstorm), ready for implementation plan
**Date:** 2026-06-25
**Issue:** #1470 (insight region primitives — the slice after the shipped format layer + ref-display fixes)
**Approach:** speculative-but-grounded — built to aegismark's abstracted need ("rank units/cohorts by a metric, surface outliers"). They ingest it and provide real-world feedback; the configurable outlier methods + render are the tuning knobs for v2.

## Background

The #1470 RFC asked for a "comparison-league" primitive. Dazzle already ships the spine it needs: every chart region compiles to one scope-aware `Repository.aggregate` → `GROUP BY` query, `bar_track` renders labelled filled tracks per row, and `box_plot` already computes per-group quartiles + outlier dots. `display: comparison` composes these into a ranked league with auto outlier-flagging.

## Goals / non-goals

**Goals**
- A declarative region that ranks rows by a metric and auto-flags statistical outliers, with no bespoke `mode: custom` HTML.
- Two modes from one primitive: aggregate-then-rank (groups) and rank-rows-directly (entities).
- Reuse the existing scope-safe aggregate spine, the format layer, the `bar_track` cell, and `box_plot`'s quartile helper. No new query semantics.

**Non-goals (v1)**
- A standalone reusable `outlier`/`rag` cell decorator for *other* displays (comparison's flag is built-in; the decorator is its own roadmap item).
- `insight_summary` (LLM narrative — separate ADR).
- Dense-ranking of ties (sequential ranks for v1).
- The deferred `dazzle inspect resolved-formats` hook.

## Modes & grammar

`display: comparison` has two modes, discriminated by the presence of `group_by:`.

**Group mode** (aggregate-then-rank) — reuses `group_by` + `aggregates`:
```
region school_league "Attendance by school":
  source: AttendanceRecord
  display: comparison
  group_by: school
  aggregates:
    rate: avg(attendance_rate)
    n: count(AttendanceRecord)
  rank_by: rate            # names one declared aggregate
  order: desc              # desc (default) | asc
  outlier_method: iqr
  limit: 20                # top-N
```

**Entity-row mode** (rank rows directly) — no `group_by`/`aggregates`:
```
region school_league "Schools":
  source: School
  display: comparison
  rank_by: attendance_rate   # names a numeric scalar field
  order: desc
  fields: [name, region, attendance_rate]   # optional extra columns
  outlier_method: sigma:2
```

**New region keys:** `rank_by:` (an aggregate name in group mode, a numeric field in entity-row mode — required), `order:` (`desc` default / `asc`), `outlier_method:` (below). Reused: `group_by`, `aggregates`, `fields`, `limit`, `filter`, `source`. Mode is inferred from `group_by`.

## Outlier flagging

Auto-flagging is **on by default** (`iqr`) — comparison's differentiator from `bar_chart`. Opt out with `outlier_method: none`.

| Method | Syntax | Flags a row when | Notes |
|---|---|---|---|
| IQR (default) | `outlier_method: iqr` | metric `< Q1 − 1.5·IQR` or `> Q3 + 1.5·IQR` | Tukey fences; robust to skew; reuses `box_plot`'s quartile helper. |
| Std-dev | `outlier_method: sigma:2` | `\|metric − mean\| > k·σ` (k default 2) | Assumes ~normal. |
| Threshold | `outlier_method: threshold:low=90,high=120` | metric `< low` or `> high` | Fixed bounds; either end optional. The literal "below target" case. |
| Off | `outlier_method: none` | never | |

**Compute** — a pure function `flag_outliers(values: list[float | None], spec: ComparisonOutlierSpec) -> list[Literal["low","high"] | None]`, run **after** the fetch over the already-materialised metric values. No I/O, no SQL change, unit-testable; lives in `render/` (reuses `box_plot`'s quartile code for IQR).

**Edge cases (pinned):**
- **Small-N guard:** `iqr`/`sigma` skip flagging when fewer than 4 rows carry a numeric value. `threshold` always applies.
- **All-equal values:** IQR = 0 → no flags.
- **`None`/missing metric:** excluded from the distribution; that row is never flagged; rendered with a blank metric cell.
- Each flag carries a direction (`low`/`high`) for the render badge.

## Render

`_build_comparison` emits a typed `Table` (reusing Table + the format layer + `bar_track`'s track cell):

| Rank | Label | Rank metric (inline bar + value) | …other columns | flag |
|---|---|---|---|---|
| 1 | Oakwood | ▇▇▇▇▇▇▇▇ 96.2% | 412 | |
| 3 | Briar | ▇▇▇ 71.4% | 201 | ⚠ low |

- **Rank** — `1..N` over sorted+limited rows; ties get sequential ranks (dense-ranking deferred).
- **Label** — `group_by` dimension (group mode) or the entity display field (entity-row mode); resolves ref display names via the #1471 `_cell_value`/`{key}_display` machinery (no UUID leak).
- **Rank-metric cell** — inline filled track (`bar_track` cell; fraction = value / max-in-set) + the value formatted through the **format layer** (`format:` applies).
- **Other columns** — extra `aggregates` (group mode) or `fields` (entity-row mode), each format-layer formatted.
- **Outlier rows** — `⚠ low` / `⚠ high` badge + row tint, from the per-row direction.

**Data to the builder:** the runtime computes, after fetch, `[{rank, label, value, bar_fraction, columns: {...}, outlier: None|"low"|"high"}]` + the scale max, threaded via `ctx` (mirroring `bar_track_rows`). The builder is pure rendering over that shape.

## Architecture & placement (`http → page → render → core`)

- **Core — IR:** `DisplayMode.COMPARISON`; `WorkspaceRegion` gains `rank_by: str | None`, `order: Literal["asc","desc"] = "desc"`, `outlier: ComparisonOutlierSpec | None`. `ComparisonOutlierSpec(method: Literal["iqr","sigma","threshold","none"], sigma_k: float | None, threshold_low: float | None, threshold_high: float | None)`.
- **Core — parser:** parse `rank_by:` / `order:` / `outlier_method:` in the region block; `outlier_method` value forms `iqr | sigma:<k> | threshold:low=<x>,high=<y> | none`.
- **Core — validation:** comparison requires `rank_by`; mode inferred from `group_by`; group mode → `rank_by` must name a declared aggregate, entity-row mode → a numeric field; the rank metric must be numeric; `order ∈ {asc,desc}`; outlier params well-formed. Violations → `E_COMPARISON_*` at `dazzle validate`.
- **http — orchestration:** group mode → existing scope-aware `Repository.aggregate` → sort by `rank_by` → `flag_outliers` → rows+max; entity-row mode → `gated_list` → sort → flag → rows. Threads the row shape into `ctx`.
- **render — pure:** `flag_outliers` (+ reuse `box_plot` quartile) and `_build_comparison`. No I/O.

## Model-driven failure-modes check (new DSL construct)

1. **Risk:** "opaque/magic computation" — ranking/outlier flags could seem arbitrary.
2. **Detector:** `dazzle validate` (`E_COMPARISON_*` + numeric-metric check); `dazzle db explain-aggregate` traces the group-mode GROUP BY.
3. **Live?** Yes — validate runs in lint/CI.
4. **Traceable?** Yes — ranking is a deterministic sort by the DSL-named `rank_by`; outliers are the DSL-named `outlier_method` over the scoped values; nothing hidden/stateful.
5. **Semantics preserved?** Yes — group mode is one scope-aware GROUP BY (Postgres aggregate, RBAC pre-aggregation, no N+1, no leak — the existing chart contract); ranking/outlier are pure post-fetch compute over already-scoped data.

→ Residual risk: low. **Documented loudly:** the league ranks over the *viewer's permitted set* (within-scope), not a global population — correct for RBAC (no leak), but authors must understand a scoped user sees a scoped ranking.

## Testing

Pure-logic-first, minimal PG:
- `flag_outliers`: each method (IQR fences, `sigma:k`, `threshold` low/high), small-N guard (n<4 → no IQR/σ flags), all-equal (no flags), `None` exclusion, low/high direction.
- Parser: `outlier_method` variants → `ComparisonOutlierSpec`; `rank_by`/`order` parse; defaults (`order=desc`, outlier `iqr`).
- Validation: each `E_COMPARISON_*` (missing `rank_by`; `rank_by` not a declared aggregate in group mode; non-numeric metric; bad `order`; malformed outlier params).
- Render: `_build_comparison` → ranked Table (rank col, inline bar, outlier badge) from a stub row shape; format-layer cell formatting; ref-display label.
- Orchestration: group-mode sort+flag over stub aggregate buckets; entity-row-mode sort+flag over stub rows.
- One example-app `display: comparison` region (group mode) + `dazzle validate` (CI e2e-smoke renders it). Group-mode aggregate leans on existing aggregate PG coverage + the scope contract.

## Sequencing

One cohesive slice → one implementation plan: IR → parser → validation → `flag_outliers` → orchestration → render → example. Ships; aegismark ingests; real-world feedback drives v2 (the configurable outlier methods + render are the tuning knobs).

## Out of scope (the rest of #1470's roadmap)

- The standalone reusable `outlier`/`rag` cell decorator for other displays — its own spec.
- `insight_summary` (LLM narrative header) — its own ADR.
- Dense-ranking of ties; the `dazzle inspect resolved-formats` hook.
