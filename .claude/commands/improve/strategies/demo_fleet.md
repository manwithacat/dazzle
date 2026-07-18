# Strategy: demo_fleet

**Lane:** example-apps
**Force path:** `/improve example-apps demo_fleet`
**Probe:** `python scripts/demo_fleet_bar.py`
**Umbrella:** GitHub **#1626** (antagonist bake-off)
**Docs:** `docs/reference/product-maturity.md` (Antagonist demo bar section)

Agent-first loop for **felt** product quality after structural
`product_maturity` residual is empty. The probe is necessary but not
sufficient for commercial bake-off — drain open #1626 P0s with stills + seeds.

## Machine probe

```bash
python scripts/demo_fleet_bar.py                 # table + next=
python scripts/demo_fleet_bar.py --status        # cycle log line
python scripts/demo_fleet_bar.py --next          # residual app id
python scripts/demo_fleet_bar.py --app <name> --json
python scripts/demo_fleet_bar.py --strict        # exit 1 if residual
# unified OBSERVE (with product + journey):
python scripts/improve_example_probes.py --status
```

Checks (machine):

| Check | Residual issue prefix |
|-------|------------------------|
| P0-4 nav | `nav_platform:` |
| P0-5 seed mins | `seed_thin:` |
| P0-6 stills | `stills_platform_only` |

**Open human P0s** (not fully scored by probe — drain via #1626 when residual=0):

| P0 | Action altitude |
|----|-----------------|
| P0-5 quality | Story titles, coherent company, queue population (not just row counts) |
| P0-6 empty hero | Default-workspace still must show rows (invoice Approval Desk) |
| P0-7 honesty | Rename false domain views (org chart, fake gallery, bullet “timeline”) |
| P0-8 design_studio | Swatches + thumbnails in stills or demote |
| P0-9 invoice desks | ≥3 rows per job desk under right tenant/persona |

## When to pick

* `product_maturity` residual already **0** and `demo_fleet_bar --next` non-empty
* Force: `/improve example-apps demo_fleet`
* #1626 has open P0-5…P0-9 and structural probes are green
* Backlog `PENDING` gap type `demo_fleet`

Skip when:

* `demo_fleet_bar` residual=0 **and** #1626 open P0s are done / deferred
* Structural product residual non-empty → run `product_maturity` first
* CI / CodeQL preemption

`budget_consumed: 0` for probe DSL/seed work.
`budget_consumed: 1` if live `qa capture` / serve seed this cycle.

## Playbook (one app or one P0 cluster per cycle)

### 1. OBSERVE

```bash
python scripts/example_product_maturity.py --status   # must be residual=0 or fix product first
python scripts/demo_fleet_bar.py --status
APP=$(python scripts/demo_fleet_bar.py --next)
gh issue view 1626 --json body -q .body | head -80   # open P0 checklist
```

If `APP` empty but #1626 still has unchecked P0-5…9:

* Prefer **invoice_ops P0-9** (empty approval desk still) or **P0-6** empty-hero
* Create backlog row: `| N | invoice_ops | demo_fleet | P0-9 empty approval queue | IN_PROGRESS | 0 | #1626 |`

If both probe residual=0 and P0-5…9 closed → PASS fleet demo mature.

### 2. ENHANCE

| Issue | Minimal patch |
|-------|----------------|
| `nav_platform` | Framework already filters; app may need curated `uses nav` without platform entities |
| `seed_thin` | Raise blueprint `row_count_default` + story `static_list` titles |
| `stills_platform_only` | Fix capture plan / purge; re-capture product desks |
| Empty job queue (P0-9) | Seed **status distribution** (submitted→Approval Desk, approved→Pay Desk); tenant scope |
| Empty hero (P0-6) | Same + re-`qa capture --above-fold` after seed |
| False view name (P0-7) | Rename workspace/surface titles to honest language |
| Design studio (P0-8) | Thumbnails/swatches in still or demote from showcase ladder |

**Seed + capture recipe** (when Postgres available):

```bash
# generate fixtures from blueprint
dazzle demo generate --project examples/$APP --format json --output-dir .dazzle/demo_data
# serve with DAZZLE_ENV=development DAZZLE_QA_MODE=1 DATABASE_URL=...
# POST /__test__/seed with X-Test-Secret from .dazzle/runtime.json (entity,id,data)
dazzle qa capture --url http://127.0.0.1:<port> --app $APP --above-fold
python scripts/demo_fleet_bar.py --app $APP --json
```

Capture plan **must** use product personas (not field archetypes) —
fixed in `dazzle.qa.capture.build_capture_plan` (#1626).

### 3. BUILD / GATE

```bash
cd examples/$APP && dazzle validate
cd ../..
python scripts/demo_fleet_bar.py --app $APP
python scripts/example_product_maturity.py --app $APP
# optional visual: inspect still for non-empty queue region
```

### 4. SHIP + ISSUE HYGIENE

Commit/push per ship discipline. On genuine P0 close:

```bash
# update #1626 checklist only when stills prove it (see prior evaluation comment)
gh issue comment 1626 --body "Closed P0-N for <app>: <evidence still path / probe>"
```

Emit:

```python
from dazzle.cli.runtime_impl.ux_cycle_signals import emit
emit(source='demo_fleet', kind='app-fixed',
     payload={'app': APP, 'gap_type': 'demo_fleet', 'commit': SHA, 'issue': 1626})
```

### Hard rules

- **One app or one P0 theme per cycle.**
- Do **not** tick #1626 boxes without still or probe evidence.
- Structural product residual non-empty → product_maturity first.
- Framework chrome/CTA bugs → one framework fix, not N apps.
- Prefer populate existing desks over new display modes.

## Relationship to other strategies

```
product_maturity (structure) → demo_fleet (felt/stills/seeds) → journey_dogfood → Tier-1 lint
```

Unified entry for every example-apps OBSERVE:

```bash
python scripts/improve_example_probes.py --status
```
