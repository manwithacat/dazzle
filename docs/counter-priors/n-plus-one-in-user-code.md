---
id: n_plus_one_in_user_code
name: N+1 queries in user app code
layer: inference
status: active
summary: >-
  Naive loops over related rows — `for order in orders: order.items.all()` —
  inside user-authored Python in `app/sync/`, `app/render/`, `app/db/`. The
  framework paths (Repository.aggregate, scope-aware joins) are clean by
  construction; user code is where the corpus prior re-introduces N+1.
  Reach for the aggregate/prefetch helpers; never enumerate.
triggers_text:
  - "loop over the rows"
  - "for each parent, fetch children"
  - "iterate over orders and get items"
  - "fetch related"
  - "N+1"
  - "n plus one"
  - "performance is fine for now"
  - "we can optimise later"
triggers_code:
  - 'for\s+\w+\s+in\s+\w+:\s*\n\s+\w+\.\w+\.all\(\)'
  - 'for\s+\w+\s+in\s+\w+:\s*\n\s+\w+_repo\.list\('
  - 'for\s+\w+\s+in\s+\w+:\s*\n\s+\w+\.fetch\('
refs:
  adrs: []
  tests: []
detectors:
  - id: PA-LLM-08
    agent: PA
    note: "covers queryset chains on loop-variable attribute access, *_repo calls with loop-variable args, and len() wrapping. Does not detect prefetched-relation suppression at AST level — author adds '# noqa: PA-LLM-08 — prefetched' when the relation is materialised upstream."
---

# N+1 queries in user app code

## The corpus prior

Django/Rails/SQLAlchemy tutorials universally introduce ORM relationships with a naive enumeration pattern: "now you can do `order.items.all()` to get the line items" — shown in a loop, with no mention of the query plan. The corpus is dominated by this shape because it's the *teaching* shape; the `select_related` / `prefetch_related` / `joinedload` follow-up appears in a later "performance" chapter that fewer readers reach.

The result: LLM-emitted user code routinely loops over a parent collection and dereferences a related collection on each iteration. The framework code path is fine — the Repository handles aggregation centrally — but the moment user code in `app/sync/`, `app/render/`, or `app/db/` reaches for the ORM-shaped enumeration, the query count goes from O(1) to O(N).

## Wrong shape

```python
# app/render/order_summary.py
def render_order_summary(orders: list[Order]) -> list[dict]:
    summaries = []
    for order in orders:
        line_count = len(order.lines.all())            # 1 query per order
        total = sum(line.total for line in order.lines.all())  # 1 more per order
        latest_payment = order.payments.order_by("-at").first()  # 1 more per order
        summaries.append({
            "id": order.id,
            "line_count": line_count,
            "total": total,
            "paid": latest_payment is not None,
        })
    return summaries
```

For 100 orders: 1 query for the order list + 300 queries inside the loop. The page that renders this summary is slow, but slow in a way that doesn't show up in any single test — each individual query is fast, the latency only emerges under load.

## Right shape

Two principles:

1. **Aggregate at the repository layer.** Dazzle ships `Repository.aggregate(group_by=..., count="...")` exactly for this case. The aggregate compiles to one scope-aware `GROUP BY` query against the underlying table — no loop, no N+1, no enumeration.
2. **When you must read individual rows, prefetch.** If the summary genuinely needs per-row data, fetch the joined slice in one query and iterate the in-memory result. Postgres handles a 5-table join trivially compared to 5 round-trips.

```python
# app/render/order_summary.py
def render_order_summary_v2(order_ids: list[UUID]) -> list[dict]:
    # One query: aggregate counts + totals per order.
    counts = order_line_repo.aggregate(
        group_by="order_id",
        count="*",
        sum="total",
        scope={"order_id__in": order_ids},
    )
    # One query: latest payment per order, via a window function or a
    # joined slice. Both available through Repository helpers.
    latest = payment_repo.latest_per_group(
        group_by="order_id",
        order_by="at",
        scope={"order_id__in": order_ids},
    )
    return [
        {
            "id": oid,
            "line_count": counts[oid]["count"],
            "total": counts[oid]["sum_total"],
            "paid": oid in latest,
        }
        for oid in order_ids
    ]
```

Two queries total, regardless of order count. The framework's aggregate path applies the scope predicate once; the join path can include a `__in=order_ids` slice that's bounded by the page size you already know.

For user-code render or sync paths that need the actual rows (not just counts), the same shape applies via prefetch helpers: fetch the related slice once, iterate the in-memory result.

## Why this matters here

The framework paths (`Repository.aggregate`, scope-aware list, chart regions in `reports.md`) are densely engineered to avoid N+1 by construction. User code is the frontier — every `app/` file the LLM writes can re-introduce the corpus shape, and there's no compile-time check for it.

The `qa trial` outputs in `improve-log.md` have repeatedly surfaced N+1 in custom render paths. The fix is always the same (move the loop into an aggregate); the prior is hard to dislodge because the tutorial-canonical shape was the loop.

A useful heuristic for review: if you see `for x in xs:` followed by `something.something_else.all()` or `repo.list(...)` inside the loop body, that's the shape. Pull the inner call up to one batched call before the loop.

## Cross-references

- `docs/reference/reports.md` — the canonical aggregate doctrine for chart/report regions.
- `src/dazzle/http/runtime/repository.py` — `Repository.aggregate` and `latest_per_group`.
- `docs/reference/project-layout.md` — the `app/<category>/` layout convention that scopes where this counter-prior applies.
- pr-review-toolkit — a review-time net for catching N+1 patterns.
