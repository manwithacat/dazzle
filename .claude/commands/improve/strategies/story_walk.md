# Strategy: story_walk

**Lane:** example-apps
**Force path:** `/improve example-apps story_walk`
**Probe:** `python scripts/story_walk_bar.py`
**Related:** #1638 scene walks, #1626 demo bar, `agent_acceptance_panel`

Agent-first dig: **landing stories must have deterministic scene walks** so
agents interact with the built app (HTTP navigate/assert), not only DSL
structure. A story is not done when `executed_by` is set — residual until a
walk covers it (and dry-run / live run is green).

## Machine probe

```bash
python scripts/story_walk_bar.py                 # table
python scripts/story_walk_bar.py --status        # cycle log line
python scripts/story_walk_bar.py --next          # residual app
python scripts/story_walk_bar.py --app NAME --json
python scripts/story_walk_bar.py --strict
python scripts/story_walk_bar.py --write-stubs   # draft YAML for missing landings
# unified OBSERVE:
python scripts/improve_example_probes.py --status
# force=example-apps story_walk when story_walk residual > 0
```

**Landing story** = accepted, not `narrative_only`, with persona, and either
`trigger: user_click` or `executed_by` on a list/queue/desk/dashboard/board surface.

**Residual when:**

| Issue | Meaning |
|-------|---------|
| `no_walks` | Landings exist, zero scene walk files |
| `missing_walk:ST-…` | Landing story id not referenced by any walk scene |
| `persona_no_walk:…` | Persona has landings but no walk uses that persona |
| `walk_load_failed:…` | YAML/schema load error |

Bar: cover at least `min(2, landing_count)` landing stories (more = deepen).

## When to pick

* `improve_example_probes` reports `story_walk residual>0` / `force=example-apps story_walk`
* Force path above
* Backlog gap type `story_walk`
* After product + demo + journey residual are empty (or in parallel if story_walk is preferred next)

Skip when:

* story_walk residual=0 for fleet (hand off to `agent_acceptance_panel` / trial_verdict)
* CI / CodeQL preemption

`budget_consumed: 0` for stub authoring + dry-run
`budget_consumed: 1` if live `dazzle test walk run` against a server this cycle

## Playbook (one app per cycle)

### 1. OBSERVE

```bash
python scripts/story_walk_bar.py --status
APP=$(python scripts/story_walk_bar.py --next)
python scripts/story_walk_bar.py --app "$APP" --json
```

Create/update backlog row: `| N | $APP | story_walk | missing landings | IN_PROGRESS | 0 | |`

### 2. ENHANCE

1. **Stub missing walks** (if none / gaps):

   ```bash
   python scripts/story_walk_bar.py --app "$APP" --write-stubs
   ```

2. **Edit stubs** for real cues:
   - `entry:` = persona default workspace or story `given:` workspace
   - `assert_any_text.texts` from story title / then: domain words
   - Keep **core-only** actions for showcase (navigate, assert_*)

3. **Validate**:

   ```bash
   dazzle test walk validate --project examples/$APP
   # or load via unit path:
   python -c "from pathlib import Path; from dazzle.testing.walk import discover_walk_paths, load_walk, validate_walk; from dazzle.core.appspec_loader import load_project_appspec; r=Path('examples/$APP'); a=load_project_appspec(r);
[print(load_walk(p).walk_id, validate_walk(load_walk(p), appspec=a)) for p in discover_walk_paths(r)]"
   ```

4. **Dry-run**:

   ```bash
   dazzle test walk run --project examples/$APP --dry-run
   ```

5. Optional **job_claims.yaml** row (`status: documented`) binding the walk.

6. **Live** (when Postgres/server available): seed + `dazzle test walk run --project examples/$APP` without dry-run; fix seeds/UX if asserts fail.

### 3. BUILD / GATE

```bash
python scripts/story_walk_bar.py --app "$APP" --strict   # exit 0 when app clear
python scripts/improve_example_probes.py --status
```

### 4. SHIP

Commit walks + claims under `examples/$APP/fixtures/`. Log:
`story_walk: $APP covered N/M landings; walks=…`

Do **not** densify desks in this strategy. Prefer walk + seed + shallow UX fix
on the story path.

## Hand-off

* Structural story bind missing → `journey_dogfood`
* Walk green but still empty hero / seeds → `demo_fleet`
* Walk green, want buyer judgment → `agent_acceptance_panel`
