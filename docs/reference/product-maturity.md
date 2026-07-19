# Product maturity (instance-level, anti-warehouse)

**Status:** fleet probe + improve gate (2026-07). Fleet residual **0/12** after
job-desk lift (invoice_ops, fieldtest_hub, design_studio, domain_join_co,
project_tracker, acme_billing, support_tickets, …).
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
| **Warehouse density** | `list_surfaces / (list_surfaces + product_workspaces)` ≤ 0.70 | Density &gt; 0.70 (deepen) or ≥ 0.85 with ≤1 product workspace (thin/critical) |
| **Job coverage** | Each product persona has bound stories **or** multi-region default workspace | Uncovered product personas |
| **CRUD without jobs** | Product workspaces exist when many list surfaces | Lists only, no product personas/workspaces |
| **Nav list share** | Compiled persona sidebars are not mostly entity lists | Avg entity-list link share &gt; 0.70 (deepen) / ≥ 0.85 (heavier) |

**Nav list share** uses `build_persona_nav` (same source as the live shell): for
each product persona, `entity_list_links / (entity_list + workspace links)`.
Auto-discover still emits entity list links; the probe **credits accessible
product workspaces** (and the landing workspace) so apps with strong job desks
are not false-flagged solely because the sidebar still lists region sources.

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

## Playbook when residual

1. **Do not** add more `mode: list` surfaces to “pass” completeness.
2. **Add** job workspaces (queues + metrics + open-to-hub) per product persona.
3. **Set** `default_workspace` to that desk (not one shared mega-workspace).
4. **Gate** access so each persona has ≥2–3 accessible product workspaces when
   auto-nav is list-heavy (nav list share).
5. Align stories `given:` and stems with the new defaults; refresh
   `SPECIFICATION.md` “Where work happens” + fingerprint.

## Warehouse Index (WI) — continuous inverse-utility gradient

After residual is **0**, improve minimizes **WI** (0–1, higher = more warehouse).
Intent: a single statistic that maps **inversely** to product utility as
expressed in DSL structure — not a claim about runtime UX or sales demos.

```bash
python scripts/example_product_maturity.py --warehouse-index
python scripts/example_product_maturity.py --next-wi
# Sibling / real apps (not only examples/):
python scripts/example_product_maturity.py --warehouse-index \
  --paths ../cyfuture ../pennydreadful ../AegisMark
```

| Component | Weight | What it measures | Anti-gaming (v2) |
|-----------|--------|------------------|------------------|
| **D** | 0.30 | list shells vs job desks | Denominator is *effective* job weight (mode×source diversity per workspace), scale-capped by entity count — empty desk sprawl does not fully dilute density |
| **N** | 0.25 | nav list-link share | Compiled `build_persona_nav`; credits accessible product workspaces |
| **L** | 0.25 | landing thinness | **Signal richness**: unique `(mode_family, source)` pairs (cap 5). Six list regions of one entity ≈ one signal |
| **J** | 0.10 | unbound stories / uncovered personas | — |
| **G** | 0.10 | lists without open-via | Platform admin lists excluded |

`WI = 0.30D + 0.25N + 0.25L + 0.10J + 0.10G`. Soft floor `wi_floor=0.25`.
Mode families collapse `list`/`queue` so parallel listish pads do not stack.

**Interpretation:** high WI ⇒ list-primary shells, thin/padded landings, soup
nav, unbound jobs, no graph hops. Low WI is **necessary** for product shape,
not sufficient for utility (see antagonist demo bar / trials below).

## What this does *not* score (yet)

- Visual kinship to Jira/Linear/GitHub Issues (needs design review or trial)
- Conversation-thread quality vs field form
- Action cost (≤N clicks) without a browser walk
- Authored `product_jobs.toml` (future: explicit job registry)
- Whether seeded data makes desks *useful* at runtime (`demo quality` / trials)
- Explicit `uses nav` that lists workspaces ahead of entity lists (probe already
  credits access; authored nav would improve *felt* UX further)

Structural pass can still *feel* warehouse if the live shell never surfaces the
job desk in the sidebar — prefer multi-workspace access + clear default landings.

## Antagonist demo bar (#1626)

Structural product maturity is **necessary but not sufficient**. An independent
artifact-only bake-off (QA screenshots + landings vs category SaaS) scored the
example fleet **~2.8 / 10** (pass line for “keep watching a sales demo” = **7.0**;
P0 target after fixes = **≥ 5.5**). Tracking: GitHub **#1626**.

| P0 | Failure | Owner altitude |
|----|---------|----------------|
| **P0-1** | Builder chrome (Reset / Saved / + Add Card) on business desks | Framework workspace shell |
| **P0-2** | CTA verbs from list titles (`New Contact List`) | Framework list adapter + surface titles |
| **P0-3** | Raw JSON 403 / wrong landing (e.g. finance on `_platform_admin`) | Framework error path + QA capture + seeds |
| **P0-4** | Platform nav pollution for product personas | Nav builder / admin injection |
| **P0-5** | Story-grade demo seeds (one coherent company) | Example blueprints |
| **P0-6** | Empty hero stills as happy-path QA names | QA capture + seed gate |
| **P0-7–9** | False domain views (org chart, gallery, timeline); invoice desks empty | Example honesty + seeds |

**Improve priority:** after structural residual is empty, drain **#1626 P0**
before STALE Tier-1 noise. Do **not** add entity list surfaces to “pass”
commercial bake-off.

### Agent loop (`/improve`)

| Force path | Strategy | Probe |
|------------|----------|-------|
| `/improve example-apps product_maturity` | `improve/strategies/product_maturity.md` | `example_product_maturity.py` |
| `/improve example-apps demo_fleet` | `improve/strategies/demo_fleet.md` | `demo_fleet_bar.py` |
| `/improve example-apps journey_dogfood` | `improve/strategies/journey_dogfood.md` | `example_journey_maturity.py` |

Every example-apps OBSERVE (and `/improve --status`) starts with the unified suite:

```bash
python scripts/improve_example_probes.py --status
# product → demo → journey preference for residual_total / next=
```

Agents should also score **felt** demo quality (persona-home seeds, metric/list
current_user residual #1632, + still floors) via the single bar — structural
residual alone can be green while desks are empty or KPIs lie:

```bash
dazzle demo quality -p examples/simple_task
dazzle demo quality -p examples --app support_tickets --json
# MCP: product_quality(operation="score", project_root="examples/invoice_ops")
```

`scripts/improve_example_probes.py` folds `product_quality` into OBSERVE so
`residual_total` is not falsely 0 when persona homes or empty-hero stills remain.

Selection order inside the lane: **product_maturity → demo_fleet → journey_dogfood → felt (product_quality) → Tier 1**.

### Antagonist residual classes (after structural green)

| Class | Symptom | Fix altitude |
|-------|---------|--------------|
| `platform_admin_landing` | product `admin` `default_workspace: _platform_admin` | Example DSL: land on a product desk + access |
| Persona-home seed residual | `current_user` region hits = 0 for stable demo UUID | Assignment-aware `*.jsonl` seeds |
| Empty-hero still | Happy-path screenshot &lt; byte floor | Re-seed + `dazzle qa capture` after seeds |

**Acceptance (showcase ready, per app):** no builder chrome on business desks;
human singular CTAs; no raw JSON errors in browser; no platform-only nav for
non-admin personas; happy-path stills non-empty with story data.

**Probe (partial, machine-checkable):**

```bash
python scripts/demo_fleet_bar.py
python scripts/demo_fleet_bar.py --strict
```

Checks P0-4 nav isolation, P0-5 blueprint min rows, and P0-6 “not only
`_platform_admin_*` stills”. Full visual re-score still needs fresh
`dazzle qa capture` after seeds.
## Relationship to other gates

| Gate | Altitude | Optimises |
|------|----------|-----------|
| validate / lint / conformance | compile | DSL completeness |
| HM surface audit | emit | pure Hyperpart markup |
| journey maturity | stories | bound agent journeys |
| **product maturity** | product path | jobs + landing + anti-warehouse |
| ux-maturity | framework | primitive defaults |
| qa trial | live instance | friction on whatever UI exists |

Improve (`example-apps` lane) prefers **product maturity residuals** before
STALE Tier-1 noise (lint field completeness) when both are open. Journey
maturity residual is next.

## CLI

```bash
# Unified /improve OBSERVE (product + demo + journey)
python scripts/improve_example_probes.py --status
python scripts/improve_example_probes.py --next
python scripts/improve_example_probes.py --strict

# Product only
python scripts/example_product_maturity.py
python scripts/example_product_maturity.py --status
python scripts/example_product_maturity.py --next
python scripts/example_product_maturity.py --app support_tickets --json
python scripts/example_product_maturity.py --strict   # CI / improve gate (exit 1 if residual)

# Demo fleet (#1626 floors)
python scripts/demo_fleet_bar.py --status
python scripts/demo_fleet_bar.py --strict

# Felt product quality (probes + persona homes + stills)
dazzle demo quality -p examples
dazzle demo quality -p examples/simple_task --strict
dazzle demo quality -p examples --app invoice_ops --json
```

## Design intent (reward structure)

**Deprecate as success metric:** every entity has list/detail/create/edit.
**Promote:** every product persona lands on a job surface; warehouse lists
are secondary (admin / settings / power-user).

Entity `mode: list` remains correct for CRUD (ux-maturity R1). Product
maturity scores whether those lists are the *primary product path*.
