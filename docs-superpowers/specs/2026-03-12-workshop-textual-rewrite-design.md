# Workshop Textual Rewrite — Design Spec

**Date**: 2026-03-12
**Status**: Approved
**Scope**: Refactor `dazzle workshop` TUI from Rich to Textual; instrument MCP handlers with structured progress

---

## Goal

Replace the current Rich-based `dazzle workshop` renderer with a Textual TUI that supports keyboard-driven drill-down into MCP tool call activity. Instrument the top ~15 handlers so they emit structured progress events. The result: every tool call becomes a browsable record with purpose, DSL context, progress timeline, summary, and pass/fail.

## Non-Goals

- Project health dashboard (future work)
- Web explorer rewrite (`explorer.py` unchanged)
- New MCP operations or tools
- Changes to `ProgressContext`, `ActivityStore` schema, or `activity.py` KG mixin

## Architecture

### Data Flow

No changes to the data pipeline. Handlers emit via `ProgressContext`, events land in SQLite `activity_events`, the Textual app polls that table.

```
MCP Handlers -> ProgressContext -> ActivityStore (SQLite activity_events table)
                                        |
                               Textual App (polls via raw SQLite, cross-session)
```

### Three-Screen Stack

1. **DashboardScreen** (default) — live active tools + recent completed history
2. **SessionScreen** — all calls in current session, grouped by tool name, collapsible
3. **CallDetailScreen** — full detail for a single tool call

Navigation: `Enter` drills in, `Esc` goes back. Textual's screen stack (`push_screen`/`pop_screen`) handles this natively.

### File Structure

| File | Action | Purpose |
|------|--------|---------|
| `src/dazzle/mcp/server/workshop.py` | Rewrite | Textual app + DashboardScreen |
| `src/dazzle/mcp/server/workshop_screens.py` | New | SessionScreen + CallDetailScreen |
| `src/dazzle/mcp/server/workshop_widgets.py` | New | Reusable widgets (ToolRow, ProgressIndicator, StatusBar) |
| `src/dazzle/mcp/server/explorer.py` | Untouched | Web explorer stays as-is |
| `src/dazzle/mcp/server/activity_log.py` | Untouched | Legacy JSONL logger kept |
| `src/dazzle/mcp/knowledge_graph/activity.py` | Untouched | SQLite activity mixin (data source) |
| `src/dazzle/mcp/server/progress.py` | Untouched | ProgressContext API unchanged |
| `src/dazzle/cli/workshop.py` | Minor edit | Import new Textual app, add graceful degradation |

### Polling

A Textual `set_interval` timer polls the SQLite `activity_events` table every 250ms (matching the current Rich implementation's poll rate). The app opens its own read-only SQLite connection to the KG database — it does NOT use `ActivityStore` (which is scoped to a single MCP session). Instead, it reuses the existing `read_new_entries_db()` pattern: raw SQL with a cursor-based `WHERE id > last_seen_id` query, reading all events across sessions. New events update reactive state on the app, triggering widget refreshes.

**Session concept**: The workshop does not create or manage sessions. "Current session" in the SessionScreen means "all events ingested since the Textual app started." If multiple MCP sessions are active, all their events appear interleaved. A future enhancement could add session filtering, but that is out of scope.

---

## Screen Designs

### DashboardScreen

Two vertically stacked panels plus a status footer.

**Active Tools Panel** (top, auto-sized to content):
- Each active tool: icon, `tool.operation`, progress bar (if numeric) or spinner, elapsed time, latest status message
- Auto-removes when `tool_end` event arrives

**Recent Completed Panel** (bottom, scrollable with cursor):
- Each row: timestamp, pass/fail icon, `tool.operation`, duration, summary annotation from `context_json`
- Highlighted cursor row, selectable via arrow keys

**Status Footer**:
- Session ID, total calls, error count, poll interval, key hints

**Key bindings:**
- `Up/Down` or `j/k` — move selection in history
- `Enter` — drill into selected call (push CallDetailScreen)
- `s` — full session view (push SessionScreen)
- `q` — quit

### SessionScreen

All tool calls in the current session, grouped by tool name.

**Groups:**
- Header: tool name, call count, total duration
- Collapsible (`Enter` on header toggles)
- Each call row: timestamp, pass/fail icon, operation, duration, summary

**Key bindings:**
- `Up/Down` or `j/k` — navigate
- `Enter` on group header — toggle collapse
- `Enter` on call row — push CallDetailScreen
- `Esc` — pop back to Dashboard

### CallDetailScreen

Full detail for a single tool call. Scrollable content.

**Sections:**
1. **Header bar** — `tool.operation`, timestamp, duration, pass/fail icon
2. **Purpose** — extracted from first `log` event message
3. **DSL Context** — project name, entity/surface counts (from `context_json` if available)
4. **Progress Timeline** — chronological list of all `progress` and `log` events for this call, with relative timestamps from call start
5. **Summary** — final summary from `context_json` or last `log` event

**Key bindings:**
- `Up/Down` — scroll content
- `Esc` — pop back to previous screen (Dashboard or Session, whichever pushed this screen)

---

## Handler Instrumentation

No changes to `ProgressContext` or `ActivityStore`. Handlers call existing APIs they currently ignore.

### What to add per handler

- `log_sync(message)` at start with purpose description
- `advance_sync(current, total, message)` at each meaningful sub-step
- Set `context_json` on completion with structured summary

### Priority handlers (15)

| Handler | What to add |
|---------|-------------|
| `pipeline.run` | `advance()` per quality step (8 steps) |
| `discovery.run` | `advance()` per entity/surface checked |
| `dsl_test.run_all` | `advance()` per test file, `context_json` with pass/fail counts |
| `dsl_test.run` | `log()` with test name, `context_json` with result |
| `e2e_test.run` | `advance()` per scenario, `context_json` with pass/fail |
| `story.coverage` | `log()` per story evaluated, `context_json` with coverage % |
| `story.rule_coverage` | `advance()` per rule, `context_json` with coverage stats |
| `sentinel.scan` | `advance()` per check category |
| `composition.audit` | `advance()` per surface audited |
| `process.coverage` | `advance()` per process, `context_json` with stats |
| `discovery.compile` | `advance()` per observation group |
| `discovery.emit` | `advance()` per DSL block generated |
| `nightly.run` | `advance()` per pipeline stage in fan-out |
| `dsl.validate` | `log()` with entity/surface counts on completion |
| `dsl.fidelity` | `advance()` per surface scored |

### Not instrumenting

Handlers that complete in <500ms: `story.get`, `story.wall`, `dsl.inspect_*`, `graph.*`, `knowledge.*`, `status.*`, `mock.*`, `api_pack.*`. Progress reporting on these would be noise.

---

## CLI & Dependency Changes

### New dependency

```toml
[project.optional-dependencies]
workshop = [
    "textual>=1.0.0",
]
```

The `dev` extra will include `workshop` for contributors.

### CLI interface

No changes to the command-line interface:

```bash
dazzle workshop                    # Textual TUI (default)
dazzle workshop --bell             # terminal bell on errors
dazzle workshop --tail 50          # cap recent history on Dashboard panel (default: 25); SessionScreen shows all
dazzle workshop --explore          # web explorer (unchanged)
dazzle workshop --port 8765        # web explorer port
```

### Graceful degradation

If `textual` is not installed:

```
Workshop TUI requires the 'workshop' extra: pip install dazzle-dsl[workshop]
```

---

## Testing Strategy

- **Unit tests** for widgets: render ToolRow with mock data, verify output
- **Unit tests** for screen logic: push/pop navigation, event handling
- **Integration test**: feed synthetic activity events into SQLite, verify DashboardScreen renders them
- **Handler instrumentation tests**: call instrumented handler, verify `progress`/`log` events in activity store
- No E2E tests (TUI testing is fragile and low-value at this stage)

---

## Existing Code Disposition

| File | Disposition |
|------|-------------|
| `workshop.py` (Rich renderer, ~750 lines) | Rewritten — Rich rendering discarded; data layer (`read_new_entries_db`, `_detect_db_path`, `_db_row_to_entry`) reused or adapted into the Textual app; `WorkshopState`/`ActiveTool`/`CompletedTool` dataclasses replaced by Textual reactive state |
| `explorer.py` (web SPA, ~800 lines) | Untouched |
| `activity_log.py` (legacy JSONL) | Untouched, backward compat |
| `activity.py` (KG mixin) | Untouched, data source |
| `progress.py` (ProgressContext) | Untouched, API unchanged |
| `cli/workshop.py` (CLI entry) | Minor edit for Textual import + graceful degradation |
