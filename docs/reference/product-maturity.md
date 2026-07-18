# Product maturity (instance-level, anti-warehouse)

**Status:** fleet probe + improve gate (2026-07).
**Probe:** `python scripts/example_product_maturity.py`
**Companion:** framework [UX maturity](ux-maturity.md) (primitives / defaults).

## The question

Framework UX maturity asks: *does Dazzle make the data-right UI the default?*
**Product maturity** asks of each **example app**:

> **Would a domain user recognise this as a product for their job —
> or as a spreadsheet warehouse with auth?**

Completeness (every entity has list/create/edit) is **not** the goal.
Persona jobs, answer-first landings, and contained CRUD are.

## Metrics (v1 — structural, machine-checkable)

| Metric | Pass when | Residual when |
|--------|-----------|---------------|
| **Answer-first landing** | Each **product** persona has `default_workspace` → real workspace with ≥1 region | Missing / empty / platform workspace for a product persona |
| **Warehouse density** | `list_surfaces / (list_surfaces + product_workspaces)` &lt; 0.70 | Density ≥ 0.70 (deepen) or ≥ 0.85 with ≤1 product workspace (thin/critical) |
| **Job coverage** | Each product persona has bound stories **or** multi-region default workspace | Uncovered product personas |
| **CRUD without jobs** | Product workspaces exist when many list surfaces | Lists only, no product personas/workspaces |

**Product personas** exclude platform ids: `admin`, `platform_admin`, `superuser`, …
**Product workspaces** exclude `_platform_*` / `admin_*` prefixes.

### Tiers

| Tier | Meaning |
|------|---------|
| `ok` | Structural product path present |
| `deepen` | Landings OK but warehouse-heavy or thin jobs |
| `thin` | High density / weak job surface |
| `critical` | No answer-first path or warehouse-only |

Higher `score` = higher residual priority for improve.

## What this does *not* score (yet)

- Visual kinship to Jira/Linear/GitHub Issues (needs design review or trial)
- Conversation-thread quality vs field form
- Action cost (≤N clicks) without a browser walk
- Authored `product_jobs.toml` (future: explicit job registry)

Structural pass can still *feel* warehouse if nav promotes entity lists
for product personas — a later probe should score **compiled nav** once
that is easy to snapshot without a live server.

## Relationship to other gates

| Gate | Altitude | Optimises |
|------|----------|-----------|
| validate / lint / conformance | compile | DSL completeness |
| HM surface audit | emit | pure Hyperpart markup |
| journey maturity | stories | bound agent journeys |
| **product maturity** | product path | jobs + landing + anti-warehouse |
| ux-maturity | framework | primitive defaults |
| qa trial | live instance | friction on whatever UI exists |

Improve should prefer **product maturity residuals** before STALE Tier-1
noise (lint field completeness) when both are open.

## CLI

```bash
python scripts/example_product_maturity.py
python scripts/example_product_maturity.py --status
python scripts/example_product_maturity.py --next
python scripts/example_product_maturity.py --app support_tickets --json
python scripts/example_product_maturity.py --strict   # CI / improve gate
```

## Design intent (reward structure)

**Deprecate as success metric:** every entity has list/detail/create/edit.
**Promote:** every product persona lands on a job surface; warehouse lists
are secondary (admin / settings / power-user).

Entity `mode: list` remains correct for CRUD (ux-maturity R1). Product
maturity scores whether those lists are the *primary product path*.
