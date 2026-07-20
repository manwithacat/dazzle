# Strategy: product_maturity

**Lane:** example-apps
**Force path:** `/improve example-apps product_maturity`
**Probe:** `python scripts/example_product_maturity.py`
**Docs:** `docs/reference/product-maturity.md`

Anti-warehouse structural maturity for example apps. Completeness (every entity
has list/create) is **not** the goal. Persona **job desks**, answer-first
landings, and lower warehouse density are.

## Machine probe

```bash
python scripts/example_product_maturity.py              # table + next=
python scripts/example_product_maturity.py --status     # cycle log line
python scripts/example_product_maturity.py --next       # single app id
python scripts/example_product_maturity.py --json
python scripts/example_product_maturity.py --app <name>
python scripts/example_product_maturity.py --warehouse-index
python scripts/example_product_maturity.py --paths ../cyfuture   # sibling/real apps
python scripts/example_product_maturity.py --strict     # exit 1 if residual
# unified OBSERVE:
python scripts/improve_example_probes.py --status
```

| Tier | Meaning | Cycle action |
|------|---------|--------------|
| `critical` | no answer-first landing / warehouse-only | Add `default_workspace` + multi-region job desk |
| `thin` | density ≥0.85 or weak product workspaces | Split role desks; diversify defaults |
| `deepen` | landings OK but density/nav still warehouse-heavy | Job desks with mixed modes/sources; curated nav |
| `ok` | structural product path present | Skip; if residual=0 minimize `wi_next` (WI gradient) |

**WI anti-gaming (v3, #1637):** L = inverse signal richness (unique
mode_family×source). D = lists / (lists + *job-backed* effective weight): only
desks that are persona `default_workspace`, appear in story `executed_by`, or
are non-orphan named product desks count; isomorphic multi-mode filter clones
(`high_ops` / `medium_ops` / …) credit **once**; orphan `*_ops` never dilute D.
Sprawl / scoreboard-language residuals flag densify residue. Hard floor:
`densify_allowed=0` when residual=0 and `wi_fleet ≤ wi_floor` — **no** D grind.
See `docs/reference/product-maturity.md`.

Fleet residual → exit **1**. Fleet mature → exit **0**.

## When to pick

* Probe `next` non-empty (prefer over STALE Tier-1 lint noise)
* Force: `/improve example-apps product_maturity`
* Unified probes report product residual before demo/journey
* Backlog `PENDING` with gap type `product_maturity`
* Residual reasons include `orphan_ops_desks`, `desk_sprawl`, `scoreboard_language`
  → **consolidate / clean**, do not densify further

Skip when residual=0:
* if `densify_allowed=1` → optional WI feature_creep on `wi_next` (job-backed only)
* if `densify_allowed=0` → hand off to `demo_fleet` / `journey_dogfood` /
  `agent_acceptance_panel` / COGNITION — **never** add another `*_ops` desk

`budget_consumed: 0` (deterministic DSL).

## Playbook (one app per cycle)

### 1. OBSERVE

```bash
python scripts/example_product_maturity.py --status
APP=$(python scripts/example_product_maturity.py --next)
```

Empty `APP` → `{status: PASS, summary: "fleet product mature"}`.

Backlog row:

`| N | <app> | product_maturity | <reasons> | IN_PROGRESS | 0 | |`

### 2. ENHANCE

| Residual | Minimal patch |
|----------|----------------|
| missing landing | `default_workspace:` → real multi-region workspace |
| high density | Add job workspaces (queues + metrics + open hub); do **not** add list surfaces |
| nav list share | Multi-workspace access for persona; workspaces credit in auto-nav |
| one shared mega-desk | Persona-specific desks (approver desk ≠ finance desk) |

Refresh `SPECIFICATION.md` “Where work happens” + fingerprint if desks change.
Align stories `given:` with defaults.

### 3. BUILD / GATE

```bash
cd examples/$APP && dazzle validate   # exit 0
cd ../..
python scripts/example_product_maturity.py --app $APP
# no residual reasons for that app
python scripts/example_product_maturity.py --strict   # optional fleet
```

### 4. SHIP

One app per cycle. Commit + push per ship discipline. Emit:

```python
from dazzle.cli.runtime_impl.ux_cycle_signals import emit
emit(source='product_maturity', kind='app-fixed',
     payload={'app': APP, 'gap_type': 'product_maturity', 'commit': SHA})
```

### Hard rules

- **One app per cycle.**
- **Never add entity lists to “pass” density.**
- **Never add isomorphic enum `*_ops` desks to “pass” D** (#1637). Prefer
  segments/filters on one job desk; consolidate orphans; strip scoreboard comments
  (`# WI D:`, `densify`, soft-cap skip narratives).
- **`densify_allowed=0` is a hard stop** — log it and leave the lane; do not soft-cap skip.
- Framework shell bugs (builder chrome always on) → `framework-ux` / #1626, not every app.
- After structural residual=0, prefer **`demo_fleet`** / **`agent_acceptance_panel`**
  over STALE Tier-1 and over WI D densify under floor.
