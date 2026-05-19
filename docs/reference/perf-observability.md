# Performance observability — `dazzle perf`

Local, on-demand OpenTelemetry tracing for any Dazzle project. Captures
a single trace run to `.dazzle/perf/<run-id>.db` and emits agent-friendly
findings on slow endpoints, slow queries, suspected N+1 patterns, slow
framework phases, and exceptions.

## Install

```bash
pip install -e ".[perf]"
```

Adds the OTel SDK + the three auto-instrumentations (`fastapi`,
`psycopg`, `asyncio`). No collector required — the bundled SQLite
exporter writes a self-contained trace file per run.

## Workflow

1. **Capture a run** while hitting one or more URLs:
   ```bash
   dazzle perf trace --url /tasks --url /users --duration 10
   ```
   Boots the app under tracing, hits the URLs, then keeps the server
   alive for `--duration` seconds so any background traffic (HTMX
   prefetch, websocket pings) also lands.

2. **Read findings**:
   ```bash
   dazzle perf report                 # Markdown, paste into Claude
   dazzle perf report --format json   # for tool-use
   ```

3. **Dig deeper**:
   ```bash
   dazzle perf list                   # past runs
   dazzle perf show --run <id>        # span tree
   ```

## What gets instrumented

**Automatically:**
- FastAPI requests
- psycopg SQL queries
- asyncio task spans

**Manually (Dazzle's hot paths):**
- `dsl.parse` — top-level parse
- `predicate.compile` — scope-rule SQL compile
- `aggregate.expression.compile` — L3 inner SQL compile
- `aggregate.build_sql` — GROUP BY composer
- `repo.aggregate` — outer Repository.aggregate call
- `region.render` — per-region render
- `fragment.emit` — fragment emission

## Agent ergonomics

The Markdown report is the source of truth for agents — designed to
paste into a Claude conversation. Section structure is stable; an
agent can rely on `## Slow endpoints`, `## Suspected N+1 patterns`,
etc., as recognisable hooks.

For programmatic use, see `docs/reference/perf-findings-schema.md`.

## MCP

The `perf` MCP tool exposes read-only operations: `list`, `report`,
`show`. The `trace` subcommand stays CLI-only because it spawns a
subprocess (ADR-0002).
