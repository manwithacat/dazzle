---
id: empty_desk_false_green
name: Empty desk with residual green (false green)
layer: inference
status: active
summary: >-
  Trusting validate green and static persona_homes residual as proof that a
  persona desk is populated. Residual can be 0 while live lists under session
  are empty (scope as: drift, wrong principal UUID, region filter). Agents
  declare demo success from residual alone; buyers see empty theater.
triggers_text:
  - "residual"
  - "persona homes"
  - "empty desk"
  - "product quality"
  - "demo ready"
  - "seed residual"
  - "my work empty"
  - "list is empty"
  - "no rows"
triggers_code:
  - 'persona_homes_residual\s*=\s*0'
  - 'residual_total\s*=\s*0'
  - 'product_quality'
  - 'score_persona_homes'
refs:
  adrs: ["0002"]
  memories: []
  pr_review_agents: []
  kb_patterns: ["empty_desk_false_green", "demo_identity", "first_principles_demo"]
  tests:
    - "tests/unit/test_issue_1630_agent_cognition.py"
detectors: []
---

# Empty desk with residual green (false green)

## The corpus prior

Agents optimise **visible green signals**. After seed, `product_quality` /
`persona_homes residual=0` and `dazzle validate` look like demo success. That
matches local-success optimisation: residual is cheap and machine-readable, so
it becomes the stop condition. The prior is *“if residual is zero, the desk is
ready for stills / buyers.”*

## Wrong shape

```text
dazzle demo reset-and-load -y   # residual 0
dazzle validate                 # green
# ship stills / claim demo ready
```

while under `role=ops_engineer` the workspace list region is empty because:

- a scope line still says `as: ops` after rename to `ops_engineer`
- persona id was domain vocabulary (`promoter`) not a STABLE key
- region filter OR was mixed-field / unsupported
- authenticate ran *before* reset (wrong principal UUIDs)

Static residual only checks **seed assignment vs filter text**, not **live
RBAC + region under session**.

## Right shape

1. Treat residual 0 as **necessary, not sufficient**.
2. After seed: authenticate with `role=` **after** reset; open default workspace
   (browser + HTMX settle) or trust `live_desk` from `reset-and-load`.
3. On empty live desk: re-check every `as:` / permit token against declared
   personas; re-check STABLE persona ids; re-check region filters.
4. `status(demo_world)` + `knowledge(concept=empty_desk_false_green)` for the
   checklist; `dazzle demo quality` for the bar.

## Why this matters here

Dazzle’s agent thesis is that tools form true beliefs about the running world.
A green residual that coexists with an empty desk is a **false belief** — worse
than missing tooling, because it stops investigation. #1630 Venue Hold Desk
proved the loop: IR green + residual green + empty Show Ops until `as:` was fixed.
