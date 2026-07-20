# Strategy: agent_acceptance_panel

**Lane:** example-apps
**Force path:** `/improve example-apps agent_acceptance_panel`
**Docs:** `docs/reference/product-maturity.md` (Agent acceptance),
`docs/recipes/agent-qa-ladder.md`, `.agents/skills/qa-trial/SKILL.md`
**Related:** #1637 (stop densify Goodhart), #1625 (agent QA ladder), #1626 (demo bar)

## Why this exists

Human product orgs use a **QA panel** that already knows the requirements and
stories: independent testers walk the product as users and accept or reject
against acceptance criteria.

In an **agent-first** workflow we do not wait for humans to define quality
(humans are L4). We still need the *function* of that panel:

| Human panel role | Agent-first substitute |
|------------------|------------------------|
| Know user stories / requirements | Authored `story` blocks + stems + `trial.toml` adoption_criteria |
| Independent of the implementer | Separate dig: panel agents ≠ densify/implement agent this cycle |
| Multi-perspective | ≥2 personas / scenarios (or ≥2 panel roles on one app) |
| Accept / reject with reasons | `submit_verdict` + criteria_scores + friction with ownership |
| Feed the backlog | JSON `auto_seed` → improve PENDING (product only) |

Structural product maturity (residual + WI) is **necessary not sufficient**.
After residual=0 and `densify_allowed=0`, acceptance panel is how we keep
improving **utility** without grinding isomorphic `*_ops` desks.

## When to pick

* Force: `/improve example-apps agent_acceptance_panel`
* `python scripts/trial_verdict_bar.py --next` non-empty (missing/failed last panel)
  — also selected via `improve_example_probes` as `force=example-apps agent_acceptance_panel`
* `residual_total=0` and `densify_allowed=0` and felt/demo/story_walk residual empty
* COGNITION path preferring `qa trial` / product_quality over pure STALE re-touch
* Backlog `PENDING` with gap type `agent_acceptance`
* After consolidating orphan ops / scoreboard language, to re-verify utility

Skip when product residual, demo residual, or story_walk residual is open
(fix structure/seeds/walks first — panel after agents can land).

`budget_consumed: 1` (live trial dig) — or `0` if only authoring/updating
`trial.toml` without a live run this cycle.

## Panel composition (minimum)

Run **one app per cycle**. Prefer showcase apps with stories + seeds.

| Seat | Source of truth | Instrument |
|------|-----------------|------------|
| **Story steward** | Product stories / domain-theory | Journey mode: `dazzle qa trial --mode journey` |
| **Pilot buyer** | `adoption_criteria` in trial.toml | Deep trial: `dazzle qa trial` (default) |
| **Coverage auditor** (optional third) | Surface inventory | `dazzle qa trial-coverage` (direct URL OK) |

Do **not** mix drive rules: coverage may deep-link; journey must use only
rendered affordances. See agent QA ladder L3.

If the app lacks `trial.toml` / adoption_criteria, **author them this cycle**
from stories (Rule 4 in qa-trial skill) and stop — live panel next cycle.

## Playbook

### 1. OBSERVE

```bash
python scripts/improve_example_probes.py --status
# require residual_total=0 (or only non-blocking warns) and densify_allowed=0
# pick APP: highest wi still under floor, or stale qa-trial capability, or force arg
APP=<name>
ls examples/$APP/trial.toml examples/$APP/dsl/*.dsl 2>/dev/null | head
```

Confirm stories exist and landings are product desks (not `_platform_admin`).

### 2. ENHANCE (acceptance artifacts only)

If missing or weak:

1. Write/refresh `trial.toml` scenarios from **jobs**, not entity CRUD.
2. Set `adoption_criteria` a founder would use for a two-week pilot.
3. Set `user_identity` + `business_context` (specific, not generic).
4. Prefer goal tasks over click scripts (qa-trial Rule 3).

Do **not** densify desks in this strategy. Structure changes only if a panel
finding has `ownership=product` and a clear minimal fix that is not another
enum ops desk.

### 3. BUILD — run the panel

```bash
cd examples/$APP
# Journey path (story steward) when stories are bound:
dazzle qa trial --mode journey --fresh-db --scenario <primary> 2>&1 | tail -80
# Deep pilot (buyer):
dazzle qa trial --fresh-db 2>&1 | tail -80
# Optional coverage inventory (auditor):
dazzle qa trial-coverage 2>&1 | tail -40
```

Collect:

* `recommend` ∈ {yes, conditional, no, unclear}
* `criteria_scores` per adoption criterion
* friction rows with `ownership` + `blocks_pilot`
* JSON sidecar `auto_seed` (medium+ × product × actionable categories only)

### 4. GATE / triage

| Outcome | Action |
|---------|--------|
| recommend=yes, no medium+ product friction | PASS — stamp capability-map `qa trial` |
| conditional / no with product friction | Seed PENDING (auto_seed) or one minimal product fix |
| seed / rbac_expected / harness ownership | Fix substrate; do not file product residual |
| framework ownership | File/hand off `framework-ux` |
| unclear + empty discovery | Backoff / Ask — do not thrash (#1625) |

### 5. SHIP

Commit trial.toml / seed / product fixes as appropriate. Emit:

```python
from dazzle.cli.runtime_impl.ux_cycle_signals import emit
emit(source='agent_acceptance_panel', kind='app-fixed',
     payload={'app': APP, 'gap_type': 'agent_acceptance',
              'recommend': RECOMMEND, 'commit': SHA})
```

Stamp `improve/capability-map.md` for `qa trial` / product_quality as USED.

## Hard rules

- **Panel ≠ implementer densify.** This strategy must not ship isomorphic
  `*_ops` desks or `# WI D:` scoreboard comments.
- **Stories and criteria first.** No free-roam deep trial on unbound narrative-only apps.
- **Human is L4.** Do not schedule humans until L1–L3 green for that pack.
- **One app per cycle.** Multi-seat panel on that app is OK; multi-app is not.
- **auto_seed discipline:** only product ownership, medium+, actionable categories.

## Relationship to other gates

| Gate | Answers |
|------|---------|
| product_maturity residual | Is there a structural product path? |
| WI / densify_allowed | Are we allowed to grind structure? (#1637 stop) |
| demo_fleet / product_quality | Are seeds and stills honest? |
| **agent_acceptance_panel** | Would a careful multi-role pilot accept this job? |
| Human L4 pack | Final commercial/sign-off when agents already green |
