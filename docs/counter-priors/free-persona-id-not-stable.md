---
id: free_persona_id_not_stable
name: Free persona id outside STABLE map
layer: inference
status: active
summary: >-
  Using domain vocabulary as persona *ids* (promoter, booker, ops) while demo
  auth and assignment seeds need STABLE_PERSONA_USER_IDS keys (requester,
  approver, ops_engineer). Display titles can be human; ids are constrained
  for demo principal UUIDs. Wrong ids → empty current_user desks after seed.
triggers_text:
  - "persona"
  - "promoter"
  - "booker"
  - "stable persona"
  - "current_user"
  - "authenticate role"
  - "demo.dazzle.local"
  - "assignment seed"
triggers_code:
  - "persona\\s+(promoter|booker|ops)\\b"
  - "STABLE_PERSONA_USER_IDS"
  - "role=.*promoter|role=.*booker"
refs:
  adrs: ["0002"]
  memories: []
  pr_review_agents: []
  kb_patterns: ["demo_identity", "stable_personas", "first_principles_demo"]
  tests:
    - "tests/unit/test_issue_1630_agent_cognition.py"
detectors: []
---

# Free persona id outside STABLE map

## The corpus prior

Agents name personas after the **domain brief** — `promoter`, `booker`,
`finance_clerk`. That is natural product language. Demo auth
(`/__test__/authenticate` with `role=`) and assignment-aware seeds only share
principal UUIDs for a **closed STABLE key set**. The corpus prior is “id = role
name in English.”

## Wrong shape

```dsl
persona promoter "Promoter":
  default_workspace: my_holds

# seeds assign rows to a1000000-… requester UUID
# authenticate role=promoter → random or non-matching principal
```

Empty “My Holds” with full tables in SQL.

## Right shape

```dsl
persona requester "Promoter":   # id = STABLE key; title = domain word
  default_workspace: my_holds
```

Use STABLE keys: member, manager, admin, requester, approver, finance,
ops_engineer, employee, … (full list on `demo_ops` / `knowledge demo_identity`).
Human titles stay free. Assignment FKs use the matching `a1000000-…` UUIDs.
Validate warns when a non-STABLE id has `default_workspace` and the app uses
`current_user` filters (#1630).

## Why this matters here

Without this prior, every first-principles multi-persona demo reinvents dual
identity (auth User vs domain User vs seed UUID). #1626/#1627/#1630 made the
STABLE map explicit; agents still invent free ids unless the KG says so at
authoring time.
