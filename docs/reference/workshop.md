# Workshop

The Workshop is a live terminal display that shows MCP tool activity as it happens. Open it in a second terminal while Claude Code works on your app to see exactly what tools are running, how long they take, and whether they succeed.

## Quick Start

```bash
dazzle workshop
```

This watches the current directory for MCP activity. You'll see active tools with progress bars, completed calls with timing, and a running tally of errors and warnings.

## Usage

```bash
dazzle workshop                              # watch current directory
dazzle workshop -p examples/simple_task      # watch a specific project
dazzle workshop --bell                       # ring terminal bell on errors
dazzle workshop --tail 50                    # show more completed entries
dazzle workshop --info                       # print the activity log path
dazzle workshop --explore                    # open web UI instead of TUI
dazzle workshop --explore --port 9000        # web UI on custom port
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-p`, `--project-dir` | `.` | Project root directory to watch |
| `-n`, `--tail` | `20` | Number of completed entries to keep visible |
| `--bell` | off | Ring terminal bell when errors occur |
| `--info` | off | Print the resolved activity log path and exit |
| `--explore` | off | Open the Activity Explorer web UI instead of the TUI |
| `--port` | `8877` | Port for the Activity Explorer HTTP server |

## Display

The Workshop TUI has three sections:

**Workbench** (top) — Tools currently running. Each shows:

- Tool name and operation (e.g. `dsl validate`, `pipeline run`)
- Elapsed time with a progress bar
- Status messages from the tool

**Done** (middle) — Scrolling list of completed tool calls. Each shows:

- Tool name and operation
- Duration in milliseconds
- Success/failure status with error details

**Status bar** (bottom) — Live counters:

- Working: number of tools currently in flight
- Done: total completed calls
- Errors: total error count
- Uptime: how long the Workshop has been running

## Configuration

The activity log location defaults to `.dazzle/mcp-activity.log` and can be overridden in your project's `dazzle.toml`:

```toml
[workshop]
log = ".dazzle/mcp-activity.log"
```

## How It Works

The Workshop reads from the MCP activity log — a structured JSONL file that the MCP server writes to as tools execute. Each log entry records tool start/end events, progress updates, errors, and warnings.

The MCP server writes activity entries automatically when tools are invoked through Claude Code. CLI commands (`dazzle validate`, `dazzle lint`, etc.) also write to the same activity store, so the Workshop shows all Dazzle activity in one place.

### Programmatic Access

The `status activity` MCP operation provides the same data for programmatic polling:

```
tool: status
operation: activity
```

## Activity Explorer

For a richer view, use the `--explore` flag to launch a web-based Activity Explorer:

```bash
dazzle workshop --explore
```

This opens an HTTP server (default port 8877) with a browser-based interface for exploring activity history, filtering by tool, and viewing detailed timing data.
