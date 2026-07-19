---
id: metric_current_user_lie
name: Metric current_user lie (list full, KPIs zero)
layer: inference
status: active
summary: >-
  Trusting workspace metric tiles that use count(... = current_user) when
  sibling list regions show rows for the same persona. Aggregate materialization
  can disagree with list filters (F10 / #1629 G5). Trust lists + stills +
  live_desk residual until product_quality residual covers metric/list pairs.
triggers_text:
  - "metrics all zero"
  - "KPI"
  - "pipeline metrics"
  - "count current_user"
  - "aggregate"
  - "vs prior"
  - "empty metrics"
triggers_code:
  - "count\\(.*current_user"
  - "display:\\s*metrics"
  - "aggregate:"
refs:
  adrs: []
  memories: []
  pr_review_agents: []
  kb_patterns: ["empty_desk_false_green", "workspace_region_filters"]
  tests: ["tests/unit/test_product_quality.py"]
detectors: []
---

# Metric current_user lie (list full, KPIs zero)

## The corpus prior

Agents treat **metrics as ground truth** for desk health. Dashboard culture
and training data say KPI tiles summarize the lists below. When lists are
populated but metrics are 0, agents still report “demo works” or “no data”
inconsistently — or chase seed bugs that are not the real failure.

## Wrong shape

```dsl
my_pipeline:
  display: metrics
  aggregate:
    draft: count(SpendRequest where status = draft and requester = current_user)
# list region for same persona shows 5 drafts
# agent: “seed failed” or “metrics prove empty”
```

Static persona_homes residual can still be 0.

## Right shape

1. **Trust order:** list/queue regions under session → stills / capture →
   metrics last.
2. On metric 0 + list > 0: assume **aggregate/current_user materialization
   footgun** until disproven (F10, #1629 G5) — not missing seeds.
3. Prefer list residual / `live_desk` / `qa capture` for demo bar.
4. **Machine residual (#1632):** `product_quality` / `dazzle demo quality`
   report `metric_list risk=` when metrics aggregates use `current_user` and
   sibling lists have seed hits (trust order still lists → stills → metrics).
   `metric_list residual=` only when seed-level metric filters score 0 while
   lists have hits (true disagreement). Risk does not thrash residual_total.

## Why this matters here

#1629 Spend Desk: employee pipeline metrics all 0 while draft lists had rows.
Cognition that “metrics are truth” produces false beliefs even when seed and
lists are correct.
