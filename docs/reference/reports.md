# Reports & Charts

Every Dazzle app reports data. A bar chart of tickets by status, a pivot of revenue by (region, product), a KPI tile showing total open incidents — all go through the same primitive: **`Repository.aggregate`**.

This page is the agent-discoverable entry point. Read this before writing a chart region.

## Mental model

```
DSL → IR → Repository.aggregate → SQL (one query) → AggregateBucket[] → Region template
```

One DSL declaration compiles to one `GROUP BY` SQL statement that evaluates the scope predicate once, returns every bucket + label + measure in a single round-trip, and hands the result to a region template for rendering. No N+1 queries, no enumeration phase, no RBAC leaks.

## Decide the shape first

Before you write DSL, pick the cardinality × visualisation:

| Visual | `display:` | Dimensions | Typical use |
|---|---|---|---|
| KPI tile | `metrics` / `summary` | 0 | "42 open tickets" |
| Bar chart | `bar_chart` | 1 | Tickets by status |
| Funnel | `funnel_chart` | 1 (ordered) | Pipeline by stage |
| Heatmap | `heatmap` | 2 | Week × hour traffic |
| Pivot table | `pivot_table` | 1..N | Alerts by (system, severity) with counts |
| Kanban | `kanban` | 1 | Tickets by status as columns |

Each consumes a different IR shape. `bar_chart` reads `group_by: <field>`. `pivot_table` reads `group_by: [<field>, <field>]`. `heatmap` reads `heatmap_rows:` + `heatmap_columns:`. `metrics` reads only `aggregate:`.

## Single-dimension (most common)

```dsl
ticket_breakdown:
  source: Ticket
  display: bar_chart
  group_by: status          # enum on Ticket
  aggregate:
    count: count(Ticket)
```

The runtime:
1. Reads `group_by: status` as a single `Dimension(name="status")`.
2. Emits `SELECT status, COUNT(*) FROM "Ticket" WHERE <scope> GROUP BY status ORDER BY status`.
3. Returns one bar per distinct status.

**FK dimensions auto-resolve.** If `status` were instead `ref TicketStatus`, the runtime adds a `LEFT JOIN "TicketStatus" fk_0 ON ...` and picks the first display field it can probe — `display_name`, then `name`, `title`, `label`, `code`. The bar label shows the human-readable value; the filter uses the FK id.

## Multi-dimension (cross-tab / pivot)

```dsl
alert_pivot:
  source: Alert
  display: pivot_table
  group_by: [system, severity]   # FK + scalar enum
  aggregate:
    count: count(Alert)
```

One row per `(system, severity)` combination. FK columns LEFT JOIN with indexed aliases (`fk_0`, `fk_1`, ...) so two FKs to the same table don't collide. Count for each cell computed in the same query. See `examples/ops_dashboard` for a working reference.

## Supported measures

| Spec | SQL | Notes |
|---|---|---|
| `count` | `COUNT(*)` | Always supported, no column arg |
| `sum:<col>` | `SUM("col")` | Numeric columns only |
| `avg:<col>` | `AVG("col")` | |
| `min:<col>` | `MIN("col")` | |
| `max:<col>` | `MAX("col")` | |

Correlated subqueries like `count(Child where parent = current_bucket)` go through a **slow path** (per-bucket queries) and are subject to N+1 cost. Prefer same-entity measures when you can.

### Fast vs slow path

The runtime picks automatically:

| Expression | Path | When to use |
|---|---|---|
| `count(<source>)` | Fast | Distribution on the source entity — this is the case #847–#851 fixed |
| `count(<source> where status = 'open')` | Fast | Filter before count, still single query |
| `count(<other> where fk = current_bucket)` | Slow | Cross-entity count per bucket; keep cardinality low |
| `avg:score` | Fast (single-dim only in v0.59.3) | Numeric measure on source |

The fast path is scope-safe by construction — one `WHERE` clause, one `GROUP BY`, no possibility of the enumeration-vs-count divergence from #847.

## Scope

**Scope always applies, pre-aggregation.** The runtime threads the user's `__scope_predicate` into the query's `WHERE` before `GROUP BY` runs. A persona who can only see rows from their own department will see counts that reflect exactly those rows — never a leak via a "total" metric or an "Other (N)" bucket.

Every scope shape `_resolve_predicate_filters` emits is aggregate-safe: direct field equality, FK-path subqueries, EXISTS / NOT EXISTS junctions, boolean compositions. Predicates that reference the GROUP BY relation itself (post-join) would need a separate code path — not supported today.

## Debugging: `dazzle db explain-aggregate`

When a chart renders wrong or empty, run:

```bash
dazzle db explain-aggregate Alert --group-by system,severity --measures count=count
```

Prints the exact SQL the framework would emit. Copy-paste into `psql` / `sqlite3`, run it manually, compare the result to what the chart shows. Three common mismatch causes:

1. **Scope narrower than expected** — explain shows no WHERE, your live session has one
2. **FK display-field probe picked a different column** — `code` when you expected `name`, for example
3. **Zero source rows in user's scope** — the chart is correct; the data isn't there

All three have been root-cause patterns; `explain-aggregate` lets authors diagnose without reading framework source.

## What NOT to do

- **Don't compute aggregates in templates.** Jinja arithmetic like `{{ rows | sum(attribute='amount') }}` loads every row into RAM, ignores scope, and breaks at scale. Use `aggregate:` with measures.
- **Don't group on high-cardinality columns without a limit.** `group_by: created_at` with a million rows returns a million buckets. Use date bucketing (future DSL feature) or `limit:` explicitly.
- **Don't mix `group_by:` and `group_by_dims:`.** They're mutually exclusive; `group_by_dims` wins when both are set but the DSL intent is confusing. Pick one form per region.
- **Don't use `count(OtherEntity where field = current_bucket)` if the source-same path works.** The sentinel-based slow path is for cross-entity measures only — same-entity counts should use `count(<source>)` and get the fast path automatically.
- **Don't reach for raw SQL.** The aggregate primitive covers the 90% case; if you need something it doesn't, file a DSL extension rather than bypass the scope contract.

## Related

- [Workspaces](workspaces.md) — where chart regions live
- [Access Control](access-control.md) — the scope predicate contract
- [Entities](entities.md) — FK fields and `display_field`
- CHANGELOG entries for [v0.59.0](../../CHANGELOG.md) (primitive), [v0.59.3](../../CHANGELOG.md) (multi-dim), [v0.59.4](../../CHANGELOG.md) (explain)
