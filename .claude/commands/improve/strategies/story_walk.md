# Strategy: story_walk

**Lane:** example-apps
**Force path:** `/improve example-apps story_walk`
**Probe:** `python scripts/story_walk_bar.py`
**Design:** `docs/superpowers/specs/2026-07-21-improve-dig-contracts-and-process-sensors-design.md`
**Related:** #1638 scene walks, #1626 demo bar, `agent_acceptance_panel`

Agent-first dig: **landing stories must have deterministic scene walks** so
agents interact with the built app (HTTP navigate/assert), not only DSL
structure. A story is not done when `executed_by` is set — residual until a
walk covers it (dry-run green; live preferred).

## Dig contract (PASS requirements)

**PASS without the contract is invalid** (self-audit + `process_dig` residual).

| # | Step | Required | Evidence |
|---|------|----------|----------|
| S1 | Residual landing story ids | MUST | `contract: stories=ST-…` |
| S2 | Cite a **map** (stem **or** SPEC/SPECIFICATION **or** story then:) | MUST | `contract: maps_cited=path` |
| S3 | Author/edit walk YAML for ≥1 missing landing | MUST | path under `fixtures/scene_walks/` |
| S4 | Walk load + validate | MUST | exit 0 |
| S5 | Walk dry-run | MUST | exit 0 |
| S6 | Live walk (seeded server) | SHOULD | exit 0 **or** `contract: live_run=skipped reason=…` |
| S7 | Job claim row | MAY | `fixtures/job_claims.yaml` |
| S8 | Re-score probe | MUST | residual ↓ or app clear |
| S9 | Dig receipt | MUST | see below |

### Required log lines

```text
contract: stories=ST-004,ST-005
contract: maps_cited=examples/contact_manager/stems/story-driven-jobs.md
contract: walk_validate=0 walk_dry_run=0
contract: live_run=skipped reason=no_db
```

### Dig receipt (MUST)

```bash
python scripts/improve_dig_receipt.py write \
  --app "$APP" --strategy story_walk --cycle N \
  --stories ST-004,ST-005 \
  --maps examples/$APP/stems/story-driven-jobs.md \
  --walks fixtures/scene_walks/user_st_004.yaml \
  --walk-validate 0 --walk-dry-run 0 \
  --live-skip no_db \
  --outcome PASS \
  --epistemic live_unproven
```

After **live** green:

```bash
python scripts/improve_dig_receipt.py mark-live --app "$APP" --walk <walk_id>
# and write receipt with --walk-live-run 0 (no --live-skip)
```

**FAIL:** clearing residual by deleting stories or inventing densify desks.
**BLOCKED:** tools prevent S4–S5 — receipt `--outcome BLOCKED` with notes.

## Machine probe

```bash
python scripts/story_walk_bar.py                 # table
python scripts/story_walk_bar.py --status
python scripts/story_walk_bar.py --next
python scripts/story_walk_bar.py --app NAME --json
python scripts/story_walk_bar.py --write-stubs
python scripts/improve_example_probes.py --status
```

**Landing story** = accepted, not `narrative_only`, persona, and `user_click`
or desk/list/queue/dashboard/board `executed_by`.

**Residual issues:**

| Issue | Meaning |
|-------|---------|
| `no_walks` / `missing_walk:ST-…` | Coverage |
| `persona_no_walk:…` | Persona without any walk |
| `walk_load_failed:…` | YAML/schema |
| `diverge:entry_ws:…` | Walk entry/home ≠ story/persona workspace |
| `diverge:persona:…` | Walk persona ≠ story persona |
| `diverge:weak_cues:…` | Empty/generic assert_any_text |
| `diverge:unknown_story:…` | Walk cites missing story id |
| `live_unproven:…` | Walk exists, never live-green (deepen) |

Bar: cover at least `min(2, landing_count)` landings.

## When to pick

* `force=example-apps story_walk` / story_walk residual > 0
* `process_dig` residual for story_walk incomplete contract
* Backlog gap type `story_walk`

`budget_consumed: 0` dry-run dig · `1` if live walk/serve

## Playbook (one app per cycle)

### 1. OBSERVE

```bash
python scripts/story_walk_bar.py --status
APP=$(python scripts/story_walk_bar.py --next)
python scripts/story_walk_bar.py --app "$APP" --json
```

### 2. ENHANCE (maps + walks)

1. Read residual story ids; open stem or SPEC once (S2).
2. `python scripts/story_walk_bar.py --app "$APP" --write-stubs` if needed.
3. Edit stubs: real workspace entry, domain `assert_any_text` from story title/then.
4. Validate + dry-run:

```bash
# validate via load path or dazzle test walk if available
python - <<'PY'
from pathlib import Path
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.testing.walk import discover_walk_paths, load_walk, validate_walk
r = Path("examples/$APP")
a = load_project_appspec(r)
for p in discover_walk_paths(r):
    w = load_walk(p)
    print(w.walk_id, validate_walk(w, appspec=a))
PY
# dry-run:
python -c "from dazzle.testing.walk.runner import run_walk_sync; from dazzle.testing.walk.loader import load_walk; from dazzle.testing.walk.discovery import discover_walk_paths; from pathlib import Path
r=Path('examples/$APP')
for p in discover_walk_paths(r):
  w=load_walk(p); print(run_walk_sync(w, base_url='http://example.test', project_root=r, dry_run=True).summary())"
```

5. Live if DB available; else `live_run=skipped` + epistemic live_unproven.
6. Write dig receipt (S9).

### 3. GATE

```bash
python scripts/story_walk_bar.py --app "$APP"
python scripts/improve_example_probes.py --status
# Close-the-loop (cycle 1261 CI red): fleet-pinned residual tiers break when
# walks land — always re-run the unit probe before push.
uv run pytest tests/unit/test_story_walk_bar.py -q
```

### 4. SHIP

Commit walks (+ optional claims). Log contract lines + residual delta.

**Do not densify** desks. Prefer walk + seed + shallow UX on the story path.

## Hand-off

* Bind stories → `journey_dogfood`
* Empty stills/seeds → `demo_fleet`
* Buyer judgment → `agent_acceptance_panel`
