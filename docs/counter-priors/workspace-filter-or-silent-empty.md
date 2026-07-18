---
id: workspace_filter_or_silent_empty
name: Workspace filter OR that empties the desk
layer: inference
status: active
summary: >-
  Writing filter: status = held or status = confirmed (or mixed-field OR)
  and expecting full SQL OR. Same-field equality OR lowers to field__in.
  Mixed-field OR is fail-closed empty. Prefer split regions when unsure.
triggers_text:
  - "filter: "
  - " or "
  - "workspace region"
  - "empty region"
  - "compound filter"
  - "status = held or"
triggers_code:
  - 'filter:\s*.+\bor\b'
  - 'status\s*=\s*\w+\s+or\s+status'
refs:
  adrs: []
  memories: []
  pr_review_agents: []
  kb_patterns: ["workspace_region_filters", "empty_desk_false_green"]
  tests:
    - "tests/unit/test_issue_1630_agent_cognition.py"
detectors: []
---

# Workspace filter OR that empties the desk

## The corpus prior

Agents write SQL-shaped filters in DSL: `status = held or status = confirmed`.
Training data treats `or` as first-class boolean algebra. Workspace region
filters historically pushed only **AND** equality to SQL; OR was a silent
no-op or wrong path — empty or unbounded desks.

## Wrong shape

```dsl
show_ops:
  source: HoldRequest
  filter: status = held or priority = high   # mixed fields
  display: list
```

or assuming arbitrary nested OR works without checking validate warnings.

## Right shape

**Same-field equality OR** (supported — lowers to `status__in`):

```dsl
filter: status = held or status = confirmed
```

**Preferred clarity** — split regions:

```dsl
held:
  source: HoldRequest
  filter: status = held
confirmed:
  source: HoldRequest
  filter: status = confirmed
```

Mixed-field OR is **fail-closed** (empty) and validate warns (#1630). Do not
trust residual alone if a region uses `or`.

## Why this matters here

Silent empty regions are the same *false green* family as scope drift: validate
passes, residual may pass, UI is empty. Agents should prefer simple filters and
know the supported OR shape before inventing compound logic.
