# Strategy: explore-subagent (substrate)

Detailed playbook for `framework-ux` lane's `missing_contracts` and `edge_cases` sub-strategies. Runs as a Claude Code Task-tool subagent (NOT a `DazzleAgent` on the direct Anthropic SDK). Cognitive work bills to the Claude Code subscription; browser work happens via stateless Playwright helper subprocess.

## Prerequisites

- Claude Code host running this very session (`Task` tool reachable)
- `examples/<canonical>/.env` with `DATABASE_URL` + `REDIS_URL`
- Postgres + Redis reachable on local dev box
- No `ANTHROPIC_API_KEY` needed — cognition runs through subscription

## Numbered playbook

### 1. Initialise per-run state directory

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import init_explore_run
import json
ctx = init_explore_run(
    example_root=Path('/Volumes/SSD/Dazzle/examples/<canonical>'),
    persona_id='<persona_id>',
)
print(json.dumps(ctx.to_dict(), indent=2))
"
```

Creates `dev_docs/ux_cycle_runs/<example>_<persona>_<run_id>/` with empty `findings.json` + generated `runner.py`. Capture printed context dict.

### 2. Boot example app via runner script (background)

```bash
python <runner_script_path>
```

Runner loads example's `.env`, boots `ModeRunner`, writes `conn.json` inside state dir, blocks on SIGTERM. **Do not wait** — run for the lifetime of the cycle.

### 3. Poll for readiness (~5s timeout)

```bash
for i in $(seq 1 20); do
  test -f <conn_path> && break
  sleep 0.5
done
cat <conn_path>
```

Grab `site_url` + `api_url` from JSON.

### 4. Log in as persona

```bash
python -m dazzle.agent.playwright_helper \
  --state-dir <state_dir> \
  login <api_url> <persona_id>
```

Verify output JSON has `"status": "logged_in"`. If `"error"` → abort, kill runner, log failure.

### 5. Build subagent mission prompt

```bash
python -c "
from dazzle.agent.missions.ux_explore_subagent import build_subagent_prompt
from dazzle.core.appspec_loader import load_project_appspec
from pathlib import Path
import os

example_root = Path('<example_root>')
app_spec = load_project_appspec(example_root)
persona = next(p for p in app_spec.personas if p.id == '<persona_id>')

components_dir = Path(os.path.expanduser('~/.claude/skills/ux-architect/components'))
existing = sorted(p.stem for p in components_dir.glob('*.md')) if components_dir.exists() else []

prompt = build_subagent_prompt(
    strategy='missing_contracts',          # or 'edge_cases'
    example_name='<example_name>',
    persona_id='<persona_id>',
    persona_label=persona.label,
    site_url='<site_url>',
    helper_command='python -m dazzle.agent.playwright_helper',
    state_dir='<state_dir>',
    findings_path='<findings_path>',
    existing_components=existing,
    start_route=persona.default_route or '/app',
    budget_calls=20,
    min_findings=3,
)
print(prompt)
"
```

### 6. Invoke Task tool

`Agent` / `Task` tool call:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `description`: `Cycle N /improve framework-ux explore: <example> <persona>`
- `prompt`: string from step 5

Wait for subagent to complete. Final message is the report; findings file is the durable artifact.

### 7. Read findings

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    ExploreRunContext, read_findings,
)
ctx = ExploreRunContext(
    example_root=Path('<example_root>'),
    example_name='<example_name>',
    persona_id='<persona_id>',
    run_id='<run_id>',
    state_dir=Path('<state_dir>'),
    findings_path=Path('<findings_path>'),
    conn_path=Path('<conn_path>'),
    runner_script_path=Path('<runner_script_path>'),
)
findings = read_findings(ctx)
print(f'proposals: {len(findings.proposals)}, observations: {len(findings.observations)}')
import json
print(json.dumps(findings.to_dict(), indent=2))
"
```

### 8. Tear down runner

```bash
pkill -TERM -f <runner_script_path> || true
```

20-min safety cap exists, but explicit teardown is cleaner. Verify `.dazzle/mode_a.lock` released against the example.

### 9. Record results

`ingest_findings` helper handles ID allocation, dedup, table insertion, formatting:

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    ExploreRunContext, read_findings,
)
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_ingest import (
    PersonaRun, ingest_findings,
)

ctxs = [
    ExploreRunContext(
        example_root=Path('<example_root>'),
        example_name='<example_name>',
        persona_id='<persona_id>',
        run_id='<run_id>',
        state_dir=Path('<state_dir>'),
        findings_path=Path('<findings_path>'),
        conn_path=Path('<conn_path>'),
        runner_script_path=Path('<runner_script_path>'),
    ),
]
runs = [
    PersonaRun(
        persona_id=ctx.persona_id,
        run_id=ctx.run_id,
        example_name=ctx.example_name,
        findings=read_findings(ctx),
    )
    for ctx in ctxs
]
result = ingest_findings(
    backlog_path=Path('/Volumes/SSD/Dazzle/dev_docs/improve-backlog.md'),
    cycle_number=<N>,
    runs=runs,
)
print('added:', result.prop_rows_added, 'proposals,', result.ex_rows_added, 'observations')
if result.proposals_skipped_as_duplicates:
    print('dedup-skipped:', result.proposals_skipped_as_duplicates)
if result.warnings:
    print('warnings:', result.warnings)
"
```

The unified `improve-backlog.md` only contains `## Proposed Components` and `## Exploration Findings` headings inside the `## Lane: framework-ux` section (those tables came verbatim from the old `ux-backlog.md`), so the helper's existing heading-scan logic finds them correctly without a `section=` parameter. If a future lane needs the same tables we'll add a section restriction then.

Helper dedups proposals by `component_name`, allocates fresh IDs, appends after last existing data row.

Findings in `dev_docs/ux_cycle_runs/<run>/findings.json` are local-only (gitignored); only backlog row updates get committed. Log entry written by hand — interpretive prose, doesn't benefit from automation.

### 10. Commit

Message: `improve: explore cycle {N} framework-ux — {proposals} proposals, {observations} observations`. Include run_id in body for future diagnosticians.

## Multi-persona fan-out

Runs one cycle per persona inside a single subprocess lifetime. Playwright launches once; each persona gets fresh `browser.new_context()` for cookie isolation. Per-persona failures (login rejected, engine crashed, anchor nav failed) → BLOCKED outcome but don't abort the loop. Aggregated `StrategyOutcome` sums per-persona findings, surfaces max independence score across all personas.
