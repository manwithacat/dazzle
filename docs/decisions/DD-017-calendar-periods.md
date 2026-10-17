# DD-017: Named calendar periods and today-anchored aggregate windows

```yaml
id: DD-017
status: PARKED
issues: [1800]
adrs: []
decided: 2026-10-17
decided_at_sha: dd64be279
parent: null
```

## One-line intent

`start_of(week | month | quarter | year)` shipped as a calendar anchor in
conditions (#1800 U21). Two further asks from the same issue are parked:
**named periods** (`start_of(term)`, `start_of(half_term)`, a project
`calendar:`) and **`window … anchored_to today`** on aggregate windows. The
fixed ISO periods cover AegisMark's "this week" strip today; both residuals
need a second shape of evidence before they earn grammar.

## Plan (what we already concluded)

### 1. `window … anchored_to today`

The #1674 windows (`week_from_monday`, `previous_week`, `last_complete_day`)
are anchored to `max(<on>)` in scope — right for meter books, where a quiet
week should still show the last week with readings. A today-anchored variant:

- **Grammar** — an optional anchor *inside the call parens*, no colon:
  `sum(Reading.value_delta window week_from_monday on taken_at anchored_to today)`;
  production `("anchored_to" ("last_reading" | "today"))?` after `on IDENT`.
  A colon form (`anchored_to: today`) collides with the `::` cast tokenisation
  inside aggregate expressions — do not use it.
- **IR** — `AggregateWindow.anchor: Literal["last_reading", "today"] = "last_reading"`.
- **Batching** — `_window_group_key` (`http/runtime/workspace_aggregation.py`)
  gains the anchor so a today-anchored and a last-reading metric never share
  one CTE.
- **Bounds** — `MeasureWindow` carries the anchor; for `today` the bounds are
  computed in Python from `calendar_today()` in the tenant timezone, and
  `_anchor_cte_sql` (`http/runtime/aggregate.py`) emits
  `SELECT %s::timestamptz AS win_start, %s::timestamptz AS win_end` instead of
  `MAX(<on>)`, so the per-measure `CASE WHEN` and the one scope-safe
  round-trip stay unchanged.
- **Counter-prior** — do not reimplement this as `where <on> >= start_of(week)`
  under the hood when the window also needs an *upper* bound (`previous_week`);
  the CTE is what keeps several windowed measures in one query.

### 2. Named periods (`start_of(term)`, `calendar:`)

Term and half-term dates are **per-school, per-year data**, not a calendar
rule: hard-coding them in the DSL hides essential complexity (MDF-01), a
`calendar:` block with literal dates grows the metamodel for one consumer
(MDF-05), and term calendars arrive from MIS integrations (MDF-08). So:

- Periods resolve against a **project-declared entity**, e.g.
  `calendar: entity Term start: starts_on end: ends_on name: label`, scoped
  like any other entity (tenant / school).
- `start_of(term)` evaluates to the `start` of the row whose
  `[start, end)` contains the tenant's today, read once per request through
  the normal repository (scope applies). No row → the condition is
  unresolved and the caller does not invent a window.
- The parser keeps rejecting `term` / `half_term` with a pointer to this DD
  until then (see `_parse_start_of` in `core/dsl_parser_impl/types.py`).
- `locale.week_start` stays out: weeks are ISO Monday everywhere (anchors,
  `date_trunc('week')`, `week_from_monday`).

## Reopen when (consumer force)

1. **Named consumer** — AegisMark declares term dates as an entity and asks
   for a "this half-term" / "this term" strip; or a second consumer (cyfuture,
   pennydreadful) needs fiscal periods that are not calendar quarters.
2. **Evidence of host workaround** — a project-side label such as "Last 7
   days" / "Since 1 Sept" standing in for a named period, or a custom
   service computing period bounds.
3. **Acceptance that unblocks** — a `metrics` region counting marks since the
   start of the current term (or a today-anchored `previous_week` total) with
   no project code, verified against Postgres.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- `start_of(week | month | quarter | year)` — `DateLiteralKind.START_OF_*`,
  conditions only (`filter:`, aggregate `where`, attention `when:`), ISO
  Monday weeks, tenant-calendar today (#1800). Docs:
  `docs/reference/reports.md` → *Calendar anchors*.
- Last-reading windows `week_from_monday` / `previous_week` /
  `last_complete_day` (#1674).
- Rolling windows `now - 7d` / `today - 7d` (v0.10.2 date arithmetic).

## Explicitly out of scope until force

- `start_of(...)` as a field default or invariant term.
- Locale-dependent week starts.
- Literal-date `calendar:` blocks in the DSL.

## Trail

| Date | Event |
|------|--------|
| 2026-10-17 | Parked (this DD) alongside the `start_of(...)` ship for #1800 |
