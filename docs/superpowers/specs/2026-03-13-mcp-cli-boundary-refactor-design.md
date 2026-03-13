# MCP/CLI Boundary Refactor

**Date**: 2026-03-13
**Status**: Approved
**Scope**: Refactor MCP server to focus on knowledge/query tools; move process/activity operations to CLI commands.

## Problem

MCP tool calls block the Claude Code conversation until they complete. Process-oriented tools (pipeline runs, test execution, LLM-powered generation, file writes) cause long blocking pauses. This conflicts with how Claude Code works best — it handles CLI commands natively with background execution, streaming output, and timeouts.

Anthropic's own guidance ([Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)) recommends MCP for context/data retrieval, not for long-running processes.

## Boundary Rule

**MCP tools** = stateless reads that return data to inform reasoning. Fast, no side effects.

**CLI commands** = anything that does work: generates content, calls LLMs, writes files, runs tests, executes pipelines.

**Test**: "Can Claude continue thinking while this runs?" If yes → CLI. If it needs the result immediately to reason → MCP.

**One exception**: `bootstrap` stays MCP (inherently conversational, needs LLM back-and-forth).

## MCP Server — After Refactor

### Kept as-is (already pure knowledge)

| Tool | Operations |
|------|-----------|
| `dsl` | validate, inspect_entity, inspect_surface, analyze, lint, fidelity, export_frontend_spec |
| `knowledge` | concept, examples, workflow, inference |
| `graph` | query, dependencies, neighbourhood, concept, inference, export, import |
| `semantics` | extract, validate_events, tenancy, compliance, analytics |
| `policy` | analyze, conflicts, coverage, simulate |
| `test_intelligence` | summary, failures, regression, coverage, context |
| `composition` | audit, capture, analyze, report, inspect_styles |
| `sitespec` | get, validate, scaffold, coherence, review, advise, get_copy, scaffold_copy, review_copy, get_theme, scaffold_theme, validate_theme, generate_tokens, generate_imagery_prompts |
| `llm` | list_intents, list_models, inspect_intent, get_config |
| `user_management` | list, create, get, update, deactivate |
| `user_profile` | observe, observe_message, get, reset |
| `status` | mcp, logs, telemetry, activity |
| `spec_analyze` | discover_entities, identify_lifecycles, extract_personas |
| `list_projects` | (single op) |
| `select_project` | (single op) |
| `get_active_project` | (single op) |
| `validate_all_projects` | (single op) |
| `bootstrap` | (single op, exception — conversational) |

Note: `llm` tool is an internal MCP tool (not listed in CLAUDE.md's public tool listing) — kept because it's a pure read.

### Slimmed — read operations kept, process operations removed

| Tool | Kept (MCP) | Removed (→ CLI) |
|------|-----------|-----------------|
| `story` | get (includes wall view), coverage, scope_fidelity | propose, save, generate_tests |
| `discovery` | coherence | run, report, compile, emit, status, verify_all_stories |
| `process` | list, inspect, coverage | propose, save, diagram |
| `rhythm` | get, list, coverage | propose, evaluate, gaps, fidelity, lifecycle |
| `test_design` | get, gaps | propose_persona, save, coverage_actions, runtime_gaps, save_runtime, auto_populate, improve_coverage |
| `pitch` | get | scaffold, generate, validate, review, update, enrich, init_assets |
| `demo_data` | get | propose, save, generate, load, validate_seeds |
| `sentinel` | findings, status, history | scan, suppress |
| `mock` | status, request_log | scenarios, fire_webhook, inject_error, scaffold_scenario |
| `api_pack` | list, search, get | generate_dsl, env_vars, infrastructure, scaffold |

Notes:
- `story wall` is a view mode of `get`, not a separate operation — stays as MCP.
- `story scope_fidelity` is a stateless analysis/read — stays as MCP per the boundary rule.
- `process list_runs` and `get_run` exist only in MCP currently and need verification during Phase 1. If they exist, they stay as MCP reads. If not, they are not in scope.

### Removed entirely from MCP (all operations → CLI)

- `dsl_test`
- `e2e_test`
- `nightly`
- `pipeline`
- `pulse`
- `contribution`

### Net result

- **Before**: ~33 tools, ~121 operations
- **After**: ~21 tools, ~58 operations (all fast, all reads)

## CLI Commands — New/Extended

All new CLI commands call the same handler functions as MCP. No logic duplication.

### CLI framework

The CLI uses **Typer** (not raw Click). All new commands follow existing Typer patterns: `@app.command()` decorators, `typer.Option`, `typer.Argument`.

### Output convention

Existing commands use `--output <file>` for JSON file output. New commands follow the same pattern. Additionally, all new commands support `--json` flag for structured JSON to stdout (useful when Claude parses output). Existing commands are NOT retrofitted — the `--json` flag applies to new commands only.

### Existing CLI coverage

Many CLI subcommand groups already exist. The following operations already have CLI equivalents and do NOT need to be created:

| CLI Group | Existing Commands |
|-----------|------------------|
| `dazzle test` | generate, run, run-all, dsl-coverage, list, create-sessions, diff-personas, populate |
| `dazzle e2e` | run, clean |
| `dazzle story` | propose, save, generate-tests, list |
| `dazzle pipeline` | run |
| `dazzle nightly` | run |
| `dazzle sentinel` | scan, findings, suppress, status |
| `dazzle pitch` | scaffold, generate, validate |
| `dazzle demo` | load, validate, reset |
| `dazzle discovery` | coherence |
| `dazzle mock` | list, run, scenario, webhook |

### Commands to add (gap-fill only)

```
dazzle story scope-fidelity                              (read — but add CLI too for consistency)
dazzle rhythm propose|evaluate|gaps|fidelity|lifecycle
dazzle process propose|save|diagram
dazzle test-design propose-persona|save|coverage-actions|runtime-gaps|save-runtime|improve-coverage
dazzle test verify-story                                 (add to existing `dazzle test` group)
dazzle e2e check-infra|coverage|list-flows|tier-guidance|run-viewport|list-viewport-specs|save-viewport-specs
dazzle discovery run|report|compile|emit|status|verify-all-stories
dazzle pulse run|radar|persona|timeline|decisions|wfs
dazzle sentinel history
dazzle pitch review|update|enrich|init-assets
dazzle demo propose|save|generate
dazzle api-pack generate-dsl|env-vars|infrastructure|scaffold
dazzle mock scenarios|fire-webhook|inject-error|scaffold-scenario
dazzle contribution templates|create|validate|examples
```

Estimated: ~50 new Typer commands (reduced from ~60 after accounting for existing coverage).

## Architecture

### Shared handler extraction

MCP handlers currently return JSON strings (not dicts), use `@wrap_handler_errors` for error formatting, and take raw `args: dict` parameters with MCP-specific patterns like `extract_progress(args)`. The extraction requires:

1. **Unwinding MCP coupling**: Each handler's core logic must be separated from JSON string serialization, MCP error wrapping, and progress context extraction.
2. **Explicit state passing**: Handlers access project state via MCP server state. Extracted functions take explicit parameters (AppSpec, project_root, etc.).
3. **Return dicts, not JSON strings**: Extracted functions return Python dicts. MCP wrappers serialize to JSON. CLI wrappers format for terminal.

Example (using Typer, matching actual codebase patterns):

```python
# src/dazzle/mcp/server/handlers/stories.py

def story_propose_impl(appspec: AppSpec, entity_name: str, ...) -> dict:
    """Pure function — the actual logic. Returns dict, not JSON string."""
    ...

# MCP wrapper (thin) — keeps @wrap_handler_errors, JSON serialization
@wrap_handler_errors
async def handle_story(operation: str, args: dict, state: ServerState) -> str:
    if operation == "propose":
        result = story_propose_impl(state.appspec, args["entity_name"], ...)
        return json.dumps(result)

# CLI wrapper (thin) — in src/dazzle/cli/story.py
@story_app.command()
def propose(
    entity_name: str = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
):
    appspec = load_project_appspec()  # from dazzle.cli.utils
    result = story_propose_impl(appspec, entity_name, ...)
    output(result, json_output)
```

### Where extracted functions live

Keep them in the existing handler files as `*_impl` functions. The MCP handler and CLI command both import from there. No new module layer needed.

### CLI project context

CLI commands access project context via `load_project_appspec()` from `dazzle.cli.utils` (already used by existing CLI commands). This reads `dazzle.toml` from the current working directory. This differs from MCP's `_resolve_project(arguments)` which uses server state, but the result is the same — an AppSpec for the active project.

### CLI shared utilities

Add a small `src/dazzle/cli/_output.py` helper:

```python
import json
import typer

def output(result: dict, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps(result, indent=2, default=str))
    else:
        # Format as readable text — keys as headers, values as content
        for key, value in result.items():
            if isinstance(value, (list, dict)):
                typer.echo(f"\n{key}:")
                typer.echo(json.dumps(value, indent=2, default=str))
            else:
                typer.echo(f"{key}: {value}")
```

## Migration Phases

### Phase 1: Extract shared handler functions

Refactor each handler file so core logic is callable without MCP context. This means:
- Extract `*_impl` functions that take typed args and return dicts
- Keep MCP wrappers that call `*_impl` and serialize to JSON
- Verify `process list_runs` and `get_run` operations actually exist; remove from scope if not

**Additive change only** — no behaviour change. Verify by running existing MCP tests.

### Phase 2: Build CLI commands

Work through tool groups one at a time, prioritised by blocking pain:
1. `pipeline`, `nightly` (most-used blocking tools — already have CLI, verify coverage)
2. `discovery`, `dsl_test`/`test`, `e2e_test` (test execution — high blocking impact)
3. `pulse`, `sentinel`, `story`, `rhythm` (generation/analysis tools)
4. `process`, `test_design`, `pitch`, `demo`, `api_pack`, `mock`, `contribution` (remaining)

For each group:
1. Add Typer commands calling extracted `*_impl` functions
2. Add `--json` flag
3. Smoke test: invoke with `--help`, invoke with valid args, check exit code

### Phase 3: Remove process operations from MCP

Split into sub-steps for safety:

**3a.** Remove tools entirely: `dsl_test`, `e2e_test`, `nightly`, `pipeline`, `pulse`, `contribution` from `tools_consolidated.py` and `handlers_consolidated.py`. One commit per tool removal.

**3b.** Slim tools: remove process operations from handler dispatch for `story`, `discovery`, `process`, `rhythm`, `test_design`, `pitch`, `demo_data`, `sentinel`, `mock`, `api_pack`. One commit per tool.

**Verification per commit**: `pytest tests/ -m "not e2e"` must pass. MCP handler tests for removed operations should be deleted in the same commit. Remaining MCP operations must still work.

**Rollback**: Each commit is independently revertable since each removes one tool or slims one tool.

### Phase 4: Update documentation

- Update CLAUDE.md with new MCP/CLI boundary explanation and reduced tool listing
- Add note to CLAUDE.md: "Process operations use CLI (`dazzle <tool> <operation>`). Knowledge operations use MCP tools."
- Update CLI `--help` text for new commands

## Testing Strategy

- **Phase 1**: Existing MCP handler tests continue to pass (refactor, not rewrite)
- **Phase 2**: Add CLI smoke tests for new commands (invoke with `--json`, check exit code and output structure). Use `typer.testing.CliRunner` for fast in-process tests.
- **Phase 3**: Delete MCP handler tests for removed operations in same commit as removal. Verify remaining MCP operations still work via their existing tests.
- **Regression**: `pytest tests/ -m "not e2e"` must pass after each phase and each commit within Phase 3.

## Risks

- **Handler coupling**: Some handlers have deep coupling to MCP state (progress context, server state, JSON string returns). Phase 1 will surface the worst cases — fix by passing state explicitly. Budget extra time for handlers with `extract_progress()` usage.
- **LLM-dependent operations**: `propose`, `generate`, `review` operations call LLMs. CLI commands need access to LLM config. Already handled by `dazzle.toml` config loading in CLI context via existing `load_project_appspec()` path.
- **Scope**: ~50 new CLI commands is substantial. The prioritised ordering in Phase 2 ensures the highest-impact tools ship first. Lower-priority tools can be deferred to follow-up work if needed.
