---
id: reseed_stable_users
name: Re-seeding STABLE User rows after reset
layer: inference
status: active
summary: >-
  Including User.jsonl rows at a1000000-… STABLE UUIDs in demo seed after
  /__test__/reset already mirrored auth users into domain User. Re-seed
  400s (id already exists) and aborts load. reset-and-load skips those rows;
  agents should seed domain data, not re-create demo principals.
triggers_text:
  - "User.jsonl"
  - "already exists"
  - "reset-and-load"
  - "demo seed"
  - "STABLE"
  - "a1000000"
triggers_code:
  - 'User\.jsonl'
  - 'a1000000-0000-4000-8000'
  - 'reset-and-load'
refs:
  adrs: ["0002"]
  memories: []
  pr_review_agents: []
  kb_patterns: ["demo_identity", "first_principles_demo"]
  tests:
    - "tests/unit/test_issue_1630_agent_cognition.py"
detectors: []
---

# Re-seeding STABLE User rows after reset

## The corpus prior

Agents seed **complete** domains: every entity including User. Fixture
mental model is “jsonl is the full world.” Test reset already creates
auth users *and* mirrors them to domain User at STABLE ids. Re-POSTing
those Users is a unique violation.

## Wrong shape

```text
POST /__test__/reset
POST /__test__/seed  # fixtures include User @ a1000000-… for each persona
→ HTTP 400 A User with this id already exists
```

Workaround folklore: delete User.jsonl by hand.

## Right shape

1. `dazzle demo reset-and-load` **skips** domain User fixtures whose id is in
   `STABLE_PERSONA_USER_IDS` **unless** the row carries required refs the auth
   mirror cannot set (e.g. multi-tenant `tenant_id: ref Tenant required`) —
   report: `skipped_stable_user_fixtures`.
2. Seed assignment-aware domain rows (Task, HoldRequest, Invoice, …) that
   **reference** STABLE ids — do not recreate scalar-only principals.
3. Non-persona domain Users (vendors, contacts) may still be seeded if their
   ids are **outside** the reserved `a1000000-…` range.
4. Seed upserts on id collision so re-capture is idempotent.

## Why this matters here

#1630 Venue Hold: full seed dir failed until User.jsonl was omitted. Encoding
the rule in the KG stops agents from thrashing on 400s after doing the
“correct” complete seed.
