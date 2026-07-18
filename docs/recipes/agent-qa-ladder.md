# Recipe: Agent QA ladder for Dazzle apps

**Audience:** downstream builders (CyFuture / AegisMark class) and Dazzle
example-app maintainers.
**Status:** framework-supported recipe (2026-07, #1625).
**Thesis:** human QA is neither necessary nor sufficient for inventory,
RBAC, golden-path, and repetitive queue dogfood — **if** the instrument
is honest and the loop closes. Humans are gated L4.

## V&V ladder

| Level | Name | Owner | Gate |
|-------|------|-------|------|
| **L0** | Schema + health | release / `dazzle validate` / `/health` | healthy |
| **L1** | Demo / golden seed | `dazzle demo` / seed scripts | golden-dominant queues |
| **L2** | Deterministic walks | contracts / interaction walks / e2e | green |
| **L3 mechanical** | Coverage inventory walk | `dazzle qa trial-coverage` | loopable in improve |
| **L3 deep** | Nested persona trial | `dazzle qa trial` (deep / journey) | friction + verdict JSON |
| **L3 outer** | In-session agent + Playwright | consumer skill (e.g. `/qa-tenant`) | same friction schema |
| **L4** | Human pack | human | **only if L1–L3 green** for that pack |
| **Ask** | Structured human intervention | consumer `OPEN.md` / issues | empty discovery + green gates |

**Hard rules**

1. No human minutes on red L1–L2.
2. No deep L3 free-roam on unbound narrative stories (prefer wall/prove/journey bind health).
3. Empty L3 discovery → **Ask / backoff**, not thrash and not “hire a human to look.”

## Instruments (do not mix drive rules)

| Mode | Measures | Drive rule | Framework entry |
|------|----------|------------|-----------------|
| **Coverage inventory** | RBAC reachability + surface completeness | Direct URL from inventory **OK** | `dazzle qa trial-inventory` / `trial-coverage` |
| **Journey / UX path** | Action-cost from landing | **Only** rendered affordances | `dazzle qa trial --mode journey` |
| **Deep pilot** | Careful evaluation + criteria scores | Free navigate after start | `dazzle qa trial` (default deep) |
| **Multi-act flow** | Cross-role continuity | Sequential acts + fact handoff | Consumer skill (framework hook later) |

Mixing coverage walks with journey metrics pollutes both signals.

## Friction schema (agent + human)

```json
{
  "category": "bug|missing|confusion|story_gap|aesthetic|praise|other",
  "severity": "low|medium|high",
  "description": "…",
  "url": "/app/…",
  "evidence": "DOM / sequence",
  "blocks_pilot": false,
  "ownership": "product|seed|rbac_expected|harness|framework|unclear"
}
```

### Auto-seed rule

Consumer improve loops should seed PENDING **only** when:

- `severity` ∈ {medium, high}
- `category` ∈ {bug, missing, confusion, story_gap}
- `ownership` = **product** (Dazzle core may also seed `framework`)

`dazzle qa trial` writes a JSON sidecar with `auto_seed` pre-filtered.

### Ownership triage (false-positive control)

| ownership | Meaning |
|-----------|---------|
| product | Real app defect |
| seed | Empty demo / missing rows |
| rbac_expected | Matrix-correct deny |
| harness | Lazy IO skeleton, actionability timeout, headless artifact |
| framework | Framework-wide defect |
| unclear | Needs human or re-probe |

## Commands

```bash
# L3 mechanical — static inventory (no server)
dazzle qa trial-inventory --app support_tickets

# L3 mechanical — live probe (server with QA mode + persona)
dazzle serve   # DAZZLE_QA_MODE=1
dazzle qa trial-coverage --app support_tickets --persona manager --base-url http://127.0.0.1:PORT

# L3 deep nested trial (gen-2 careful pilot)
cd examples/support_tickets
dazzle qa trial --scenario manager_evaluation --fresh-db --llm-driver grok-cli
# → dev_docs/qa-trial-*.md + .json (auto_seed included)

# Journey instrument (affordance-only)
dazzle qa trial --scenario manager_evaluation --mode journey --fresh-db

# Domain-theory hook
dazzle qa trial-hypotheses --app support_tickets
```

## Closed loop (KPI)

Trial value = frictions that become PENDING → ship → re-measure.

Suggested consumer KPIs:

- **Closed product findings per agent-hour**
- **False-positive rate** (harness/seed mis-owned rows that hit PENDING)
- **Empty streak** → open structured Ask (not endless HOUSEKEEPING)

## Harness-artifact appendix

Do **not** file as product without checking:

1. **IntersectionObserver lazy regions** — headless may leave skeletons; scroll into view first.
2. **Playwright actionability timeouts** on HTMX/Alpine transitions ≠ dead product.
3. **Stale non-fingerprinted assets** after deploy — hard refresh / cache bust.
4. **Magic-link sessions not tenant-bound** — HTMX/search 403 while page GET works (framework class).
5. **Generic `/app/<entity>` 404** with workspace `source:` / route-override — check alternate reachability + `dazzle rbac matrix`.
6. **Expected RBAC deny** — trust matrix over persona folklore.

## Domain theory (optional)

Create `agent/domain-theory/<domain>.md` with falsifiable IDs:

```markdown
## H-A1 — Manager sees critical queue without spreadsheet math
## H-C1 — Customer can complete signing without staff
```

Deep trial reports should mark confirmed | falsified | inconclusive.
Empty mechanical runs with “hypotheses untested” are honest.

## Example app application

| App | Recipe touch |
|-----|----------------|
| support_tickets | Flagship gen-2 `manager_evaluation`; domain-theory stub; inventory via CLI |
| others | `dazzle qa trial-inventory --app <name>`; upgrade trial.toml over time |

## See also

- `docs/reference/qa-trial-gen2.md` — nested trial gen-2 posture
- `docs/reference/qa-trial-patterns.md` — early multi-app findings
- `.agents/skills/qa-trial/SKILL.md` — authoring skill
- GitHub #1625 — CyFuture + AegisMark field notes
