# MCP/CLI Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move process/activity MCP operations to CLI commands, keeping knowledge/query operations as MCP tools, to eliminate conversation blocking.

**Architecture:** Extract pure `*_impl` functions from MCP handlers. CLI commands (Typer) and MCP wrappers both call these functions. Remove process operations from MCP tool registration. Each handler file keeps its extracted logic — no new module layer.

**Tech Stack:** Python 3.12+, Typer (CLI), custom MCP server, pytest

**Spec:** `docs/superpowers/specs/2026-03-13-mcp-cli-boundary-refactor-design.md`

---

## File Structure

### New files to create

| File | Purpose |
|------|---------|
| `src/dazzle/cli/_output.py` | Shared CLI output formatting (JSON/text) |
| `src/dazzle/cli/rhythm.py` | Rhythm CLI commands |
| `src/dazzle/cli/process_cli.py` | Process CLI commands (named `process_cli` for clarity since `process` is a Python stdlib module) |
| `src/dazzle/cli/test_design.py` | Test design CLI commands |
| `src/dazzle/cli/pulse.py` | Pulse CLI commands |
| `src/dazzle/cli/api_pack.py` | API pack CLI commands |
| `src/dazzle/cli/contribution.py` | Contribution CLI commands |

### Existing files to modify

| File | Changes |
|------|---------|
| `src/dazzle/cli/__init__.py` | Register new Typer apps |
| `src/dazzle/cli/story.py` | Add `scope-fidelity` command |
| `src/dazzle/cli/discovery.py` | Add `run`, `report`, `compile`, `emit`, `status`, `verify-all-stories` commands |
| `src/dazzle/cli/e2e.py` | Add `check-infra`, `coverage`, `list-flows`, `tier-guidance`, `run-viewport`, `list-viewport-specs`, `save-viewport-specs` commands |
| `src/dazzle/cli/testing.py` | Add `verify-story` command |
| `src/dazzle/cli/sentinel.py` | Add `history` command (note: file is `sentinel.py`, not `sentiment.py`) |
| `src/dazzle/cli/pitch.py` | Add `review`, `update`, `enrich`, `init-assets` commands |
| `src/dazzle/cli/demo.py` | Add `propose`, `save`, `generate` commands |
| `src/dazzle/cli/mock.py` | Add `scenarios`, `fire-webhook`, `inject-error`, `scaffold-scenario` commands |
| `src/dazzle/mcp/server/tools_consolidated.py` | Remove process tool definitions |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Remove process operation dispatch |
| `.claude/CLAUDE.md` | Update MCP/CLI boundary docs |

### Handler files to refactor (extract `*_impl` functions)

All in `src/dazzle/mcp/server/handlers/`:

| Handler | Lines | Operations to extract |
|---------|-------|----------------------|
| `stories.py` | 742 | propose, save, generate_tests |
| `rhythm.py` | 1166 | propose, evaluate, gaps, fidelity, lifecycle |
| `process/proposals.py` | 531 | propose |
| `process/storage.py` | 228 | save |
| `process/diagrams.py` | 366 | diagram |
| `discovery/missions.py` | 293 | run |
| `discovery/compiler.py` | 134 | compile, report |
| `discovery/emitter.py` | 95 | emit |
| `discovery/status.py` | 272 | status, verify_all_stories |
| `dsl_test.py` | 836 | all ops |
| `pipeline.py` | 221 | run |
| `nightly.py` | 296 | run |
| `pulse.py` | 1213 | all ops |
| `sentinel.py` | 192 | scan, suppress |
| `pitch.py` | 794 | scaffold, generate, validate, review, update, enrich, init_assets |
| `demo_data.py` | 686 | propose, save, generate, load, validate_seeds |
| `api_packs.py` | 358 | generate_dsl, env_vars, infrastructure, scaffold |
| `mock.py` | 346 | scenarios, fire_webhook, inject_error, scaffold_scenario |
| `contribution.py` | 683 | all ops |
| `test_design/proposals.py` | 239 | propose_persona |
| `test_design/persistence.py` | 142 | save |
| `test_design/coverage.py` | 553 | coverage_actions, runtime_gaps, save_runtime, improve_coverage |
| `testing.py` | 692 | e2e_test operations (check_infra, run, run_agent, coverage, etc.) |
| `viewport_testing.py` | 133 | run_viewport, list_viewport_specs, save_viewport_specs |

**Notes:**
- `process list_runs` and `get_run`: Verify these exist in `process/storage.py` during Phase 1. If present, keep as MCP reads. If not, remove from scope.
- `auto_populate` (test_design): Already covered by existing `dazzle test populate` CLI command. No new extraction or CLI command needed.
- `demo_data load` and `validate_seeds`: Already covered by existing `dazzle demo load` and `dazzle demo validate` CLI commands. No new CLI commands needed, but `*_impl` extraction still needed for the MCP removal in Phase 3.

---

## Chunk 1: Foundation — Output Helper and Handler Extraction Pattern

This chunk establishes the shared CLI output utility and demonstrates the extraction pattern on two handlers (one simple, one complex) before scaling to the rest.

### Task 1.1: Create CLI output helper

**Files:**
- Create: `src/dazzle/cli/_output.py`
- Test: `tests/unit/test_cli_output.py`

- [ ] **Step 1: Write the test**

```python
# tests/unit/test_cli_output.py
import json
from dazzle.cli._output import format_output


def test_format_output_json():
    result = {"status": "ok", "count": 3}
    text = format_output(result, as_json=True)
    assert json.loads(text) == result


def test_format_output_text():
    result = {"status": "ok", "items": ["a", "b"]}
    text = format_output(result, as_json=False)
    assert "status: ok" in text
    assert "items:" in text


def test_format_output_nested_dict():
    result = {"meta": {"version": "1.0"}}
    text = format_output(result, as_json=False)
    assert "meta:" in text
    assert "version" in text


def test_format_output_empty():
    text = format_output({}, as_json=False)
    assert text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_output.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.cli._output'`

- [ ] **Step 3: Implement the output helper**

```python
# src/dazzle/cli/_output.py
"""Shared CLI output formatting for MCP-migrated commands."""
from __future__ import annotations

import json


def format_output(result: dict, *, as_json: bool = False) -> str:
    """Format a handler result dict for terminal output.

    Args:
        result: Dict returned by a handler *_impl function.
        as_json: If True, return indented JSON. Otherwise human-readable text.

    Returns:
        Formatted string ready for typer.echo().
    """
    if as_json:
        return json.dumps(result, indent=2, default=str)

    lines: list[str] = []
    for key, value in result.items():
        if isinstance(value, (list, dict)):
            lines.append(f"{key}:")
            lines.append(json.dumps(value, indent=2, default=str))
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cli_output.py -v`
Expected: All 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/_output.py tests/unit/test_cli_output.py
git commit -m "feat(cli): add shared output formatting helper for MCP-migrated commands"
```

---

### Task 1.2: Extract sentinel handler (simple — 192 lines, minimal coupling)

Sentinel is the simplest handler — good proof-of-concept for the extraction pattern.

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/sentinel.py`
- Test: Run existing tests

- [ ] **Step 1: Read the handler file**

Read `src/dazzle/mcp/server/handlers/sentinel.py` in full to understand current structure.

- [ ] **Step 2: Extract `*_impl` functions**

For each operation (`scan`, `findings`, `suppress`, `status`, `history`), extract the core logic into a function with typed parameters that returns a dict. The MCP handler becomes a thin wrapper.

Pattern:
```python
# Before (inside handler dispatch):
#   appspec = load_project_appspec(project_root)
#   results = run_scan(appspec, ...)
#   return json.dumps({"findings": results})

# After:
def sentinel_scan_impl(project_root: Path, ...) -> dict:
    """Run sentinel scan. Returns findings dict."""
    appspec = load_project_appspec(project_root)
    results = run_scan(appspec, ...)
    return {"findings": results}

# MCP wrapper:
async def handle_sentinel(operation, args, state):
    if operation == "scan":
        result = sentinel_scan_impl(state.project_root, ...)
        return json.dumps(result)
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `pytest tests/unit/ -k sentinel -v`
Expected: All existing sentinel tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/sentinel.py
git commit -m "refactor(sentinel): extract *_impl functions from MCP handler"
```

---

### Task 1.3: Add sentinel `history` CLI command (gap-fill)

**Files:**
- Modify: `src/dazzle/cli/sentinel.py`

- [ ] **Step 1: Read the existing CLI file**

Read `src/dazzle/cli/sentinel.py` to understand existing patterns (`scan`, `findings`, `suppress`, `status`).

- [ ] **Step 2: Add `history` command**

Follow the pattern of existing commands in the file. Import `sentinel_history_impl` from the handler. Add:

```python
@sentinel_app.command()
def history(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show sentinel scan history."""
    from dazzle.mcp.server.handlers.sentinel import sentinel_history_impl
    from dazzle.cli._output import format_output

    project_root = _get_project_root()
    result = sentinel_history_impl(project_root)
    typer.echo(format_output(result, as_json=json_output))
```

- [ ] **Step 3: Smoke test**

Run: `dazzle sentinel history --help`
Expected: Shows help text with `--json` option

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/sentiment.py
git commit -m "feat(cli): add sentinel history command"
```

---

### Task 1.4: Extract pipeline handler (simple — 221 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/pipeline.py`

- [ ] **Step 1: Read and extract**

Read `src/dazzle/mcp/server/handlers/pipeline.py`. Extract `pipeline_run_impl(project_root: Path, ...) -> dict`.

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/unit/ -k pipeline -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/mcp/server/handlers/pipeline.py
git commit -m "refactor(pipeline): extract *_impl functions from MCP handler"
```

---

### Task 1.5: Extract nightly handler (simple — 296 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/nightly.py`

- [ ] **Step 1: Read and extract**

Read `src/dazzle/mcp/server/handlers/nightly.py`. Extract `nightly_run_impl(project_root: Path, ...) -> dict`.

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/unit/ -k nightly -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/mcp/server/handlers/nightly.py
git commit -m "refactor(nightly): extract *_impl functions from MCP handler"
```

---

## Chunk 2: Extract Remaining Handlers

Scale the extraction pattern to all remaining handlers. Each task follows the same read → extract → test → commit pattern established in Chunk 1.

### Task 2.1: Extract stories handler (742 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/stories.py`

- [ ] **Step 1: Read handler**

Read `src/dazzle/mcp/server/handlers/stories.py` in full.

- [ ] **Step 2: Extract process operations**

Extract: `story_propose_impl`, `story_save_impl`, `story_generate_tests_impl`. Keep read operations (`get`, `wall`, `coverage`, `scope_fidelity`) as-is inside the handler — they stay as MCP.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k story -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/stories.py
git commit -m "refactor(story): extract process *_impl functions from MCP handler"
```

---

### Task 2.2: Extract rhythm handler (1166 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract process operations**

Extract: `rhythm_propose_impl`, `rhythm_evaluate_impl`, `rhythm_gaps_impl`, `rhythm_fidelity_impl`, `rhythm_lifecycle_impl`. Keep reads (`get`, `list`, `coverage`) as-is.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k rhythm -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py
git commit -m "refactor(rhythm): extract process *_impl functions from MCP handler"
```

---

### Task 2.3: Extract process handlers (directory — 2257 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/process/proposals.py`
- Modify: `src/dazzle/mcp/server/handlers/process/storage.py`
- Modify: `src/dazzle/mcp/server/handlers/process/diagrams.py`

- [ ] **Step 1: Read all three files**
- [ ] **Step 2: Extract process operations**

Extract: `process_propose_impl` (from proposals.py), `process_save_impl` (from storage.py), `process_diagram_impl` (from diagrams.py). Keep reads (`list`, `inspect`, `list_runs`, `get_run`, `coverage`) as-is.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k process -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/process/
git commit -m "refactor(process): extract process *_impl functions from MCP handlers"
```

---

### Task 2.4: Extract discovery handlers (directory — 1010 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/discovery/missions.py`
- Modify: `src/dazzle/mcp/server/handlers/discovery/compiler.py`
- Modify: `src/dazzle/mcp/server/handlers/discovery/emitter.py`
- Modify: `src/dazzle/mcp/server/handlers/discovery/status.py`

- [ ] **Step 1: Read all files**
- [ ] **Step 2: Extract all process operations**

Extract: `discovery_run_impl`, `discovery_report_impl`, `discovery_compile_impl`, `discovery_emit_impl`, `discovery_status_impl`, `discovery_verify_all_stories_impl`. Keep `coherence` as-is (stays MCP).

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k discovery -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/discovery/
git commit -m "refactor(discovery): extract process *_impl functions from MCP handlers"
```

---

### Task 2.5: Extract dsl_test handler (836 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/dsl_test.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract all operations**

Extract: `dsl_test_generate_impl`, `dsl_test_run_impl`, `dsl_test_run_all_impl`, `dsl_test_coverage_impl`, `dsl_test_list_impl`, `dsl_test_verify_story_impl`, `dsl_test_diff_personas_impl`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k "dsl_test or test_dsl" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/dsl_test.py
git commit -m "refactor(dsl_test): extract *_impl functions from MCP handler"
```

---

### Task 2.6: Extract e2e_test handlers (testing.py + viewport_testing.py)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/testing.py`
- Modify: `src/dazzle/mcp/server/handlers/viewport_testing.py`

- [ ] **Step 1: Read both handler files**
- [ ] **Step 2: Extract all operations**

Extract from `testing.py`: `e2e_check_infra_impl`, `e2e_run_impl`, `e2e_run_agent_impl`, `e2e_coverage_impl`, `e2e_list_flows_impl`, `e2e_tier_guidance_impl`.

Extract from `viewport_testing.py`: `e2e_run_viewport_impl`, `e2e_list_viewport_specs_impl`, `e2e_save_viewport_specs_impl`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k "e2e" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/testing.py src/dazzle/mcp/server/handlers/viewport_testing.py
git commit -m "refactor(e2e_test): extract *_impl functions from MCP handlers"
```

---

### Task 2.7: Extract pulse handler (1213 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/pulse.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract all operations**

Extract: `pulse_run_impl`, `pulse_radar_impl`, `pulse_persona_impl`, `pulse_timeline_impl`, `pulse_decisions_impl`, `pulse_wfs_impl`. All operations move to CLI.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k pulse -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/pulse.py
git commit -m "refactor(pulse): extract *_impl functions from MCP handler"
```

---

### Task 2.8: Extract pitch handler (794 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/pitch.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract process operations**

Extract: `pitch_scaffold_impl`, `pitch_generate_impl`, `pitch_validate_impl`, `pitch_review_impl`, `pitch_update_impl`, `pitch_enrich_impl`, `pitch_init_assets_impl`. Keep `get` as-is.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k pitch -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/pitch.py
git commit -m "refactor(pitch): extract process *_impl functions from MCP handler"
```

---

### Task 2.9: Extract demo_data handler (686 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/demo_data.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract process operations**

Extract: `demo_propose_impl`, `demo_save_impl`, `demo_generate_impl`, `demo_load_impl`, `demo_validate_seeds_impl`. Keep `get` as-is.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k demo -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/demo_data.py
git commit -m "refactor(demo_data): extract process *_impl functions from MCP handler"
```

---

### Task 2.10: Extract api_packs handler (358 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/api_packs.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract process operations**

Extract: `api_pack_generate_dsl_impl`, `api_pack_env_vars_impl`, `api_pack_infrastructure_impl`, `api_pack_scaffold_impl`. Keep `list`, `search`, `get` as-is.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k api_pack -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/api_packs.py
git commit -m "refactor(api_pack): extract process *_impl functions from MCP handler"
```

---

### Task 2.11: Extract mock handler (346 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/mock.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract process operations**

Extract: `mock_scenarios_impl`, `mock_fire_webhook_impl`, `mock_inject_error_impl`, `mock_scaffold_scenario_impl`. Keep `status`, `request_log` as-is.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k mock -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/mock.py
git commit -m "refactor(mock): extract process *_impl functions from MCP handler"
```

---

### Task 2.12: Extract contribution handler (683 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/contribution.py`

- [ ] **Step 1: Read handler**
- [ ] **Step 2: Extract all operations**

Extract: `contribution_templates_impl`, `contribution_create_impl`, `contribution_validate_impl`, `contribution_examples_impl`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k contribution -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/contribution.py
git commit -m "refactor(contribution): extract *_impl functions from MCP handler"
```

---

### Task 2.13: Extract test_design handlers (directory — 1147 lines)

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/test_design/proposals.py`
- Modify: `src/dazzle/mcp/server/handlers/test_design/persistence.py`
- Modify: `src/dazzle/mcp/server/handlers/test_design/coverage.py`

- [ ] **Step 1: Read all files**
- [ ] **Step 2: Extract process operations**

Extract: `test_design_propose_persona_impl`, `test_design_save_impl`, `test_design_coverage_actions_impl`, `test_design_runtime_gaps_impl`, `test_design_save_runtime_impl`, `test_design_improve_coverage_impl`. Keep `get` and `gaps` as-is.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -k test_design -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/test_design/
git commit -m "refactor(test_design): extract process *_impl functions from MCP handlers"
```

---

### Task 2.14: Full regression check

- [ ] **Step 1: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All ~3400 tests PASS

- [ ] **Step 2: Run linter**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean

- [ ] **Step 3: Run type checker**

Run: `mypy src/dazzle`
Expected: Clean (or no new errors)

- [ ] **Step 4: Commit any formatting fixes**

```bash
git add -u && git commit -m "style: formatting fixes from handler extraction"
```

---

## Chunk 3: Build CLI Commands

Add Typer commands for all gap operations. Prioritised by blocking impact.

### Task 3.1: Discovery CLI commands (highest blocking impact)

**Files:**
- Modify: `src/dazzle/cli/discovery.py`

- [ ] **Step 1: Read existing CLI file**

Read `src/dazzle/cli/discovery.py` (121 lines). Note existing `coherence` command pattern.

- [ ] **Step 2: Add commands**

Add `run`, `report`, `compile`, `emit`, `status`, `verify-all-stories` commands following the existing pattern in each file. Each imports the corresponding `*_impl` function from the discovery handler modules.

**Important — project root resolution**: Each existing CLI file has its own pattern for resolving the project root (e.g., `_resolve_root(manifest)` with a `--manifest` option, or `_resolve_project_root()`). Follow the convention already in the file you're modifying. Do NOT introduce a new pattern.

```python
@discovery_app.command()
def run(
    mode: str = typer.Option("full", help="Discovery mode: full, entity, workflow"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run discovery mission."""
    from dazzle.mcp.server.handlers.discovery.missions import discovery_run_impl
    from dazzle.cli._output import format_output

    project_root = _resolve_project_root()
    result = discovery_run_impl(project_root, mode=mode)
    typer.echo(format_output(result, as_json=json_output))
```

Repeat for `report`, `compile`, `emit`, `status`, `verify-all-stories`.

- [ ] **Step 3: Smoke test**

Run: `dazzle discovery --help`
Expected: Shows all commands including new ones

Run: `dazzle discovery run --help`
Expected: Shows `--mode` and `--json` options

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/discovery.py
git commit -m "feat(cli): add discovery run/report/compile/emit/status/verify-all-stories commands"
```

---

### Task 3.2: E2E test CLI commands

**Files:**
- Modify: `src/dazzle/cli/e2e.py`

- [ ] **Step 1: Read existing CLI file**

Read `src/dazzle/cli/e2e.py` (291 lines).

- [ ] **Step 2: Add gap commands**

Add: `check-infra`, `coverage`, `list-flows`, `tier-guidance`, `run-viewport`, `list-viewport-specs`, `save-viewport-specs`. Follow existing patterns in the file.

- [ ] **Step 3: Smoke test**

Run: `dazzle e2e --help`
Expected: Shows all commands

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/e2e.py
git commit -m "feat(cli): add e2e check-infra/coverage/list-flows/run-viewport commands"
```

---

### Task 3.3: DSL test `verify-story` command

**Files:**
- Modify: `src/dazzle/cli/testing.py`

- [ ] **Step 1: Read existing CLI file**

Read `src/dazzle/cli/testing.py` — find the `test_app` Typer app and existing command patterns.

- [ ] **Step 2: Add `verify-story` command**

```python
@test_app.command()
def verify_story(
    story_id: str = typer.Argument(..., help="Story ID to verify"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Verify a story against DSL tests."""
    from dazzle.mcp.server.handlers.dsl_test import dsl_test_verify_story_impl
    from dazzle.cli._output import format_output

    project_root = _resolve_project_root()
    result = dsl_test_verify_story_impl(project_root, story_id=story_id)
    typer.echo(format_output(result, as_json=json_output))
```

- [ ] **Step 3: Smoke test**

Run: `dazzle test verify-story --help`
Expected: Shows help

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/testing.py
git commit -m "feat(cli): add test verify-story command"
```

---

### Task 3.4: Pulse CLI commands (new file)

**Files:**
- Create: `src/dazzle/cli/pulse.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create pulse CLI module**

```python
# src/dazzle/cli/pulse.py
"""Pulse health-check and analytics CLI commands."""
from __future__ import annotations

import typer

from dazzle.cli._output import format_output

pulse_app = typer.Typer(help="Project health pulse checks")


def _resolve_project_root():
    from dazzle.cli.utils import load_project_appspec
    # Follow existing pattern for project root resolution
    ...


@pulse_app.command()
def run(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run full project pulse check."""
    from dazzle.mcp.server.handlers.pulse import pulse_run_impl
    ...
```

Add commands: `run`, `radar`, `persona`, `timeline`, `decisions`, `wfs`.

- [ ] **Step 2: Register in `__init__.py`**

Read `src/dazzle/cli/__init__.py`, find where other apps are registered, add:

```python
from dazzle.cli.pulse import pulse_app
app.add_typer(pulse_app, name="pulse")
```

- [ ] **Step 3: Smoke test**

Run: `dazzle pulse --help`
Expected: Shows all 6 commands

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/pulse.py src/dazzle/cli/__init__.py
git commit -m "feat(cli): add pulse commands (run/radar/persona/timeline/decisions/wfs)"
```

---

### Task 3.5: Rhythm CLI commands (new file)

**Files:**
- Create: `src/dazzle/cli/rhythm.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create rhythm CLI module**

Follow same pattern as Task 3.4. Commands: `propose`, `evaluate`, `gaps`, `fidelity`, `lifecycle`.

- [ ] **Step 2: Register in `__init__.py`**
- [ ] **Step 3: Smoke test**

Run: `dazzle rhythm --help`

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/rhythm.py src/dazzle/cli/__init__.py
git commit -m "feat(cli): add rhythm commands (propose/evaluate/gaps/fidelity/lifecycle)"
```

---

### Task 3.6: Process CLI commands (new file)

**Files:**
- Create: `src/dazzle/cli/process_cli.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create process CLI module**

Name the file `process_cli.py` for clarity (avoids confusion with Python's `multiprocessing.process`). Commands: `propose`, `save`, `diagram`.

- [ ] **Step 2: Register in `__init__.py`**

```python
from dazzle.cli.process_cli import process_app
app.add_typer(process_app, name="process")
```

- [ ] **Step 3: Smoke test**
- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/process_cli.py src/dazzle/cli/__init__.py
git commit -m "feat(cli): add process commands (propose/save/diagram)"
```

---

### Task 3.7: Test design CLI commands (new file)

**Files:**
- Create: `src/dazzle/cli/test_design.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create test_design CLI module**

Commands: `propose-persona`, `save`, `coverage-actions`, `runtime-gaps`, `save-runtime`, `improve-coverage`.

- [ ] **Step 2: Register in `__init__.py`**
- [ ] **Step 3: Smoke test**
- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/test_design.py src/dazzle/cli/__init__.py
git commit -m "feat(cli): add test-design commands"
```

---

### Task 3.8: Story `scope-fidelity` command

**Files:**
- Modify: `src/dazzle/cli/story.py`

- [ ] **Step 1: Read existing file and add command**

Note: `scope_fidelity` lives in the process handler package (`handlers/process/scope_fidelity.py`) but is dispatched as a story MCP operation. The CLI command goes under `story` for user-facing consistency.

```python
@story_app.command()
def scope_fidelity(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check story scope fidelity."""
    # Cross-package import: logic lives in process/ handlers but exposed as story CLI
    from dazzle.mcp.server.handlers.process.scope_fidelity import scope_fidelity_impl
    ...
```

- [ ] **Step 2: Smoke test**
- [ ] **Step 3: Commit**

```bash
git add src/dazzle/cli/story.py
git commit -m "feat(cli): add story scope-fidelity command"
```

---

### Task 3.9: Sentinel `history` command

Already done in Task 1.3. Skip.

---

### Task 3.10: Pitch gap commands

**Files:**
- Modify: `src/dazzle/cli/pitch.py`

- [ ] **Step 1: Read existing file, add gap commands**

Add: `review`, `update`, `enrich`, `init-assets`.

- [ ] **Step 2: Smoke test**
- [ ] **Step 3: Commit**

```bash
git add src/dazzle/cli/pitch.py
git commit -m "feat(cli): add pitch review/update/enrich/init-assets commands"
```

---

### Task 3.11: Demo gap commands

**Files:**
- Modify: `src/dazzle/cli/demo.py`

- [ ] **Step 1: Read existing file, add gap commands**

Add: `propose`, `save`, `generate`.

- [ ] **Step 2: Smoke test**
- [ ] **Step 3: Commit**

```bash
git add src/dazzle/cli/demo.py
git commit -m "feat(cli): add demo propose/save/generate commands"
```

---

### Task 3.12: API pack CLI commands (new file)

**Files:**
- Create: `src/dazzle/cli/api_pack.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create api_pack CLI module**

Commands: `generate-dsl`, `env-vars`, `infrastructure`, `scaffold`.

- [ ] **Step 2: Register in `__init__.py`**
- [ ] **Step 3: Smoke test**
- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/api_pack.py src/dazzle/cli/__init__.py
git commit -m "feat(cli): add api-pack commands (generate-dsl/env-vars/infrastructure/scaffold)"
```

---

### Task 3.13: Mock gap commands

**Files:**
- Modify: `src/dazzle/cli/mock.py`

- [ ] **Step 1: Read existing file, add gap commands**

Add: `scenarios`, `fire-webhook`, `inject-error`, `scaffold-scenario`.

- [ ] **Step 2: Smoke test**
- [ ] **Step 3: Commit**

```bash
git add src/dazzle/cli/mock.py
git commit -m "feat(cli): add mock scenarios/fire-webhook/inject-error/scaffold-scenario commands"
```

---

### Task 3.14: Contribution CLI commands (new file)

**Files:**
- Create: `src/dazzle/cli/contribution.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create contribution CLI module**

Commands: `templates`, `create`, `validate`, `examples`.

- [ ] **Step 2: Register in `__init__.py`**
- [ ] **Step 3: Smoke test**
- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/contribution.py src/dazzle/cli/__init__.py
git commit -m "feat(cli): add contribution commands (templates/create/validate/examples)"
```

---

### Task 3.15: Full regression check

- [ ] **Step 1: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All ~3400 tests PASS

- [ ] **Step 2: Run linter and type checker**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/ && mypy src/dazzle`

- [ ] **Step 3: Commit any fixes**

```bash
git add -u && git commit -m "style: formatting fixes from CLI command additions"
```

---

## Chunk 4: Remove MCP Process Operations and Update Docs

### Task 4.1: Remove `dsl_test` from MCP

**Files:**
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`

- [ ] **Step 1: Read both files, find `dsl_test` registration**

Search for `dsl_test` in `tools_consolidated.py` and `handlers_consolidated.py`.

- [ ] **Step 2: Remove tool definition and handler dispatch**

Remove the `dsl_test` tool definition from `tools_consolidated.py` and the handler dispatch from `handlers_consolidated.py`.

- [ ] **Step 3: Delete or update relevant MCP tests**

Find tests that test the `dsl_test` MCP tool. Delete tests for removed operations.

Run: `pytest tests/unit/ -k "dsl_test" -v` to find affected tests.

- [ ] **Step 4: Run regression**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "refactor(mcp): remove dsl_test tool from MCP server"
```

---

### Task 4.2: Remove `e2e_test` from MCP

Same pattern as Task 4.1. Remove from `tools_consolidated.py` and `handlers_consolidated.py`.

- [ ] **Step 1: Remove tool and handler**
- [ ] **Step 2: Update tests**
- [ ] **Step 3: Run regression**
- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(mcp): remove e2e_test tool from MCP server"
```

---

### Task 4.3: Remove `nightly` from MCP

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): remove nightly tool from MCP server"
```

---

### Task 4.4: Remove `pipeline` from MCP

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): remove pipeline tool from MCP server"
```

---

### Task 4.5: Remove `pulse` from MCP

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): remove pulse tool from MCP server"
```

---

### Task 4.6: Remove `contribution` from MCP

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): remove contribution tool from MCP server"
```

---

### Task 4.7: Slim `story` MCP tool — remove process operations

**Files:**
- Modify: `src/dazzle/mcp/server/tools_consolidated.py` — remove `propose`, `save`, `generate_tests` from story tool schema
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py` — remove dispatch for those operations

- [ ] **Step 1: Remove operations from tool definition and dispatch**
- [ ] **Step 2: Update tests**
- [ ] **Step 3: Run regression**
- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(mcp): slim story tool — remove propose/save/generate_tests operations"
```

---

### Task 4.8: Slim `discovery` MCP tool — keep only `coherence`

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim discovery tool — keep only coherence operation"
```

---

### Task 4.9: Slim `process` MCP tool

Remove: `propose`, `save`, `diagram`. Keep: `list`, `inspect`, `list_runs`, `get_run`, `coverage`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim process tool — remove propose/save/diagram operations"
```

---

### Task 4.10: Slim `rhythm` MCP tool

Remove: `propose`, `evaluate`, `gaps`, `fidelity`, `lifecycle`. Keep: `get`, `list`, `coverage`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim rhythm tool — remove process operations"
```

---

### Task 4.11: Slim `test_design` MCP tool

Remove: `propose_persona`, `save`, `coverage_actions`, `runtime_gaps`, `save_runtime`, `auto_populate`, `improve_coverage`. Keep: `get`, `gaps`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim test_design tool — remove process operations"
```

---

### Task 4.12: Slim `pitch` MCP tool

Remove: `scaffold`, `generate`, `validate`, `review`, `update`, `enrich`, `init_assets`. Keep: `get`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim pitch tool — keep only get operation"
```

---

### Task 4.13: Slim `demo_data` MCP tool

Remove: `propose`, `save`, `generate`, `load`, `validate_seeds`. Keep: `get`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim demo_data tool — keep only get operation"
```

---

### Task 4.14: Slim `sentinel` MCP tool

Remove: `scan`, `suppress`. Keep: `findings`, `status`, `history`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim sentinel tool — remove scan/suppress operations"
```

---

### Task 4.15: Slim `mock` MCP tool

Remove: `scenarios`, `fire_webhook`, `inject_error`, `scaffold_scenario`. Keep: `status`, `request_log`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim mock tool — remove process operations"
```

---

### Task 4.16: Slim `api_pack` MCP tool

Remove: `generate_dsl`, `env_vars`, `infrastructure`, `scaffold`. Keep: `list`, `search`, `get`.

- [ ] **Step 1-4: Same pattern**

```bash
git commit -m "refactor(mcp): slim api_pack tool — remove process operations"
```

---

### Task 4.17: Final regression and docs update

- [ ] **Step 1: Full regression**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All PASS

- [ ] **Step 2: Update CLAUDE.md**

Update `.claude/CLAUDE.md`:
- Replace the condensed MCP tool description with the new tool listing (knowledge tools only)
- Add a section explaining the MCP/CLI boundary rule
- Add a CLI command reference for process operations
- Update the version if bumping

- [ ] **Step 3: Commit docs**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md with MCP/CLI boundary and new tool listing"
```

- [ ] **Step 4: Final full regression**

Run: `pytest tests/ -m "not e2e" -x -q && ruff check src/ tests/ && mypy src/dazzle`
Expected: All clean
