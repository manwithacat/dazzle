# Strategy: visual_tier2_subagent (example-apps Tier 2)

Detailed playbook for `example-apps` lane's **Tier 2** visual-QA explore. Runs as a Claude Code Task-tool subagent (NOT a Claude API call). Cognitive work bills to the Claude Code subscription; browser work (screenshot capture) happens via `dazzle qa capture` per app.

Replaces the API-bound screenshot-scrape CLI (`qa visual`, removed in the same commit that introduced this strategy) — capture is now `dazzle qa capture` + this subagent.

## Prerequisites

- Claude Code host running this very session (`Task` tool reachable)
- Each example app boots cleanly via `dazzle serve --local` (or via the per-cycle runner pattern from `explore-subagent.md`)
- No `ANTHROPIC_API_KEY` needed — cognition runs through subscription

## Numbered playbook

### 1. Initialise per-run state directory

```bash
RUN_TS=$(date -u +%Y%m%dT%H%M%SZ)
STATE_DIR=$(pwd)/dev_docs/ux_cycle_runs/visual_tier2_${RUN_TS}
mkdir -p "${STATE_DIR}"
MANIFEST="${STATE_DIR}/manifest.json"
FINDINGS="${STATE_DIR}/findings.json"
echo "STATE_DIR=${STATE_DIR}"
echo "MANIFEST=${MANIFEST}"
echo "FINDINGS=${FINDINGS}"
```

Capture these paths — the rest of the playbook references them.

### 2. Capture screenshots across the fleet

For each example app (`simple_task`, `contact_manager`, `support_tickets`, `ops_dashboard`, `fieldtest_hub`):

1. Boot the app in another terminal (or via `dazzle e2e env start <app>`).
2. Run `dazzle qa capture` pointing at the running URL with `--manifest <MANIFEST>`.

The CLI appends each app's screens to the same JSON manifest. Re-running the command for the same app overwrites that app's entry.

```bash
cd examples/<app> && dazzle qa capture \
    --url http://localhost:<port> \
    --manifest "${MANIFEST}"
```

If a per-cycle ModeRunner already provides a managed server (cf. `explore-subagent.md` step 2), reuse it — that's the cheaper substrate. The CLI flags are identical.

Verify the manifest is non-empty and has an entry for every app:

```bash
python -c "
import json, sys
m = json.load(open('${MANIFEST}'))
apps = [a['app'] for a in m.get('apps', [])]
total = sum(len(a['screens']) for a in m.get('apps', []))
print(f'manifest covers {len(apps)} apps, {total} screens: {apps}')
sys.exit(0 if total > 0 else 1)
"
```

### 3. Build the subagent mission prompt

```bash
python -c "
import json
from pathlib import Path
from dazzle.qa.evaluate import build_subagent_prompt
manifest = json.loads(Path('${MANIFEST}').read_text())
prompt = build_subagent_prompt(manifest, findings_path='${FINDINGS}')
Path('${STATE_DIR}/prompt.txt').write_text(prompt)
print(prompt)
" > "${STATE_DIR}/prompt.txt"
```

The prompt instructs the subagent to Read each screenshot, evaluate against `dazzle.qa.categories.CATEGORIES`, and Write a JSON findings array to `${FINDINGS}`.

### 4. Invoke the Task tool

Single dispatch, one subagent for the whole fleet (~25-50 screenshots):

- `subagent_type`: `general-purpose`
- `model`: omit — inherit the session model (visual perception + evaluation is judgment work; CLAUDE.md Subagent Model Policy)
- `description`: `Cycle N /improve example-apps visual Tier 2 — fleet sweep`
- `prompt`: contents of `${STATE_DIR}/prompt.txt`

Wait for completion. The subagent's final message echoes the findings array; the durable artifact is the file at `${FINDINGS}`.

### 5. Read findings

```bash
test -f "${FINDINGS}" && python -c "
import json
data = json.load(open('${FINDINGS}'))
print(f'{len(data)} findings')
for f in data[:5]:
    print(f'  [{f.get(\"severity\")}] {f.get(\"app\")}: {f.get(\"category\")} — {f.get(\"description\")[:80]}')
"
```

If `${FINDINGS}` is missing or empty, the subagent crashed or judged the fleet clean. Either is a valid outcome.

### 6. Ingest into the example-apps backlog

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.visual_tier2_ingest import ingest_visual_findings
result = ingest_visual_findings(
    findings_path=Path('${FINDINGS}'),
    manifest_path=Path('${MANIFEST}'),
    backlog_path=Path('/Volumes/SSD/Dazzle/dev_docs/improve-backlog.md'),
)
print(f'rows_added={result.rows_added} rows_reinforced={result.rows_reinforced}')
for w in result.warnings:
    print(f'warn: {w}')
"
```

Ingest rules (see `visual_tier2_ingest.py`):
- Dedup key is `(app, category, location[:60])`. Re-runs of the same drift bump the existing row's `seen=K` counter.
- Findings are sorted `high → medium → low` before insertion, so the lane naturally picks worst-first.
- Row shape: `| N | <app> | visual_quality | [<category>] <description> at <location> | PENDING | 0 | seen=1, screenshot=<path>, ts=<...> |`.

### 7. Tear down

If a managed server is still running (step 2 booted it), shut it down:

```bash
# whatever your step-2 boot recipe uses
pkill -TERM -f "<runner-or-serve-pattern>" || true
```

The state directory under `dev_docs/ux_cycle_runs/` is gitignored — leave it for diagnostics.

### 8. Record cycle outcome

The driver appends an entry to `dev_docs/improve-log.md`:

```
## Cycle N — YYYY-MM-DD — lane: example-apps — outcome: EXPLORED
Sub-strategy: visual_tier2_subagent. Manifest: <N> apps, <M> screens. Findings: <K> total (<high>/<med>/<low>). Ingested: <added> new rows, <reinforced> rows reinforced. Run dir: ${STATE_DIR}.
```

## Budget

This strategy increments the shared `/improve` explore budget by **5** — one heavy dispatch with multi-screen vision work. Don't run it every cycle; let signal-driven re-runs (a new `ux-component-shipped` or `dazzle-updated`) motivate the next sweep.

## When to skip

- The example-apps backlog has open `PENDING` rows from a previous sweep → drain those first via the lane's normal cycle, then re-sweep.
- Explore budget near cap (≥90/100) → wait until next reset.
- A previous sweep within the last 24h reinforced ≥80% of its findings as duplicates → signal is converged; re-run only after a framework change.
