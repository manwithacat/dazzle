---
id: faker_seed_over_story_spine
name: Faker dumps over assignment-aware story seeds
layer: inference
status: active
summary: >-
  Preferring generated `.dazzle/demo_data` faker CSVs over authored
  `dsl/seeds/demo_data/*.jsonl` for persona desks. Faker uses random User
  ids that break STABLE assignment FKs; story seeds pin a1000000-… principals.
  reset-and-load prefers story seeds when present.
triggers_text:
  - "demo generate"
  - "faker"
  - "demo_data"
  - "assignment"
  - "persona home"
  - "jsonl"
  - "story seed"
triggers_code:
  - '\.dazzle/demo_data'
  - 'dsl/seeds/demo_data'
  - 'dazzle demo generate'
refs:
  adrs: ["0002"]
  memories: []
  pr_review_agents: []
  kb_patterns: ["demo_identity", "first_principles_demo", "empty_desk_false_green"]
  tests:
    - "tests/unit/test_mcp_session_1628.py"
detectors: []
---

# Faker dumps over assignment-aware story seeds

## The corpus prior

Agents run `dazzle demo generate` and load whatever lands in
`.dazzle/demo_data/` (CSV with random UUIDs and lorem copy). That matches
“generate fixtures and load them” tutorials, not assignment-aware demos.

## Wrong shape

```text
dazzle demo generate --output-dir .dazzle/demo_data
dazzle demo reset-and-load   # picks faker CSV if it shadows story seeds
→ User ids are random; Task.assigned_to never matches STABLE principal
→ My Work / Approval Desk empty under role= authenticate
```

## Right shape

1. Author **`dsl/seeds/demo_data/*.jsonl`** with STABLE principal UUIDs on
   assignment FKs (`assigned_to`, `submitted_by`, …).
2. `dazzle demo reset-and-load` precedence: story seeds → project
   `demo_data/` → generated `.dazzle/demo_data/` last.
3. Use generate only for volume/stress data that is not persona-home critical.

## Why this matters here

#1626 recapture: story seeds made simple_task/support residual 0; faker
shadowing produced seed 400s and empty hero stills. Encode the path so
agents stop “fixing” empty desks with more generate runs.
