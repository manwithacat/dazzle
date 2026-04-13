# E2E Environment — Mode A Reference

Mode A is the Dazzle developer one-shot harness: launch a live example app,
run something against it (usually the fitness engine), tear down when done.

## Quick start

```bash
cd examples/support_tickets
cp .env.example .env
# Edit .env to point at your local Postgres + Redis
dazzle e2e env start support_tickets
```

The command blocks until Ctrl+C. While it runs:

- UI at `http://localhost:<hashed-port>` (printed by the command)
- API at `http://localhost:<hashed-port>` (also printed)
- Lock file at `examples/support_tickets/.dazzle/mode_a.lock` prevents
  two concurrent Mode A runs against the same example
- Log captured to `examples/support_tickets/.dazzle/e2e-logs/mode_a-<ts>.log`

## Commands

```bash
dazzle e2e env start <example>     # Launch Mode A, block until Ctrl+C
dazzle e2e env status [<example>]  # Show lock/runtime/log state
dazzle e2e env stop <example>      # SIGTERM → SIGKILL the lock holder
dazzle e2e env logs <example>      # Tail the latest captured log
```

## Flags

- `--mode=a` — Mode name (only Mode A ships in v1).
- `--fresh` — Force DB reset + upgrade + demo generate, rebuilding any
  baseline snapshot along the way.
- `--personas=admin,agent` — Comma-separated persona IDs. Auto-sets
  `DAZZLE_ENV=development` and `DAZZLE_QA_MODE=1` so persona magic-link
  login works via QA mode (#768).
- `--db-policy=preserve|fresh|restore` — Override the mode default.
  Mode A defaults to `preserve`.

## DB state policies

| Policy | What it does |
|--------|-------------|
| `preserve` (default) | No-op. You own the DB state. |
| `fresh` | `reset → upgrade → demo generate` before launch. Slow (~15s) but deterministic seed. |
| `restore` | Lazy-build + restore from `examples/<app>/.dazzle/baselines/baseline-<rev>-<hash12>.sql.gz`. First run is slow; subsequent runs are ~1s. |

## Snapshot primitives

The snapshot/restore machinery is also exposed as standalone CLI commands:

```bash
dazzle db snapshot baseline      # Capture current state as a baseline
dazzle db restore baseline       # Restore the current-hash baseline
dazzle db snapshot-gc --keep=3   # Delete older baseline files
```

The `baseline` name uses hash-tagging (filename encodes the Alembic head
and a SHA of demo fixture files) so schema or fixture changes
automatically invalidate cached files. Other names (`dazzle db snapshot
mid-refactor`) use verbatim filenames — useful for capturing a known
state before a destructive experiment.

## MCP surface (read-only)

Agents can enumerate modes and inspect state via the `e2e` MCP tool.
Operations:

- `list_modes` — full registry of runner modes
- `describe_mode` — details for one mode
- `status` — lock holder, runtime ports, last log tail
- `list_baselines` — hash-tagged snapshot files + which matches current key

Process operations (start/stop) are **CLI-only** per ADR-0002.

## Troubleshooting

**`ModeAlreadyRunningError: lock held by pid N`** — another Mode A
instance holds the lock. Either wait for it to finish, or run
`dazzle e2e env stop <example>` to kill it. Stale locks older than
15 minutes are auto-reaped.

**`RuntimeFileTimeoutError: .dazzle/runtime.json did not appear`** —
`dazzle serve` started but never wrote `runtime.json`. Usually means
`.env` is missing or `DATABASE_URL` points at an unreachable DB. Check
`dazzle e2e env logs <example>` for the subprocess stderr tail.

**`HealthCheckTimeoutError: /docs did not return 200`** — `runtime.json`
appeared but `/docs` never responded. Usually a migration failed or
Postgres isn't reachable. Check the log tail.

**`PgDumpNotInstalledError`** — `pg_dump`/`pg_restore` missing from
PATH. Install with `brew install postgresql@16` (macOS) or
`apt-get install postgresql-client-16` (Debian/Ubuntu).

## Design notes

See `docs/superpowers/specs/2026-04-14-e2e-environment-strategy-design.md`
for the full design, including Modes B/C/D (sketched but not wired in v1).

- **Mode B** (CI gate) — planned for v0.55.x
- **Mode C** (long-running dev env) — planned for v0.56.x
- **Mode D** (autonomous loop) — planned when the fitness methodology
  is mature enough to benefit from periodic regression checks
