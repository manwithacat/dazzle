# E2E Environment Strategy — Design

**Date:** 2026-04-14
**Status:** Draft — user review pending
**Author:** Dazzle core + Claude (brainstorm)
**Supersedes:** Ad-hoc subprocess launch in `dazzle.qa.server.connect_app` (which has a hardcoded-port bug this spec fixes)
**Related:**
- ADR-0002 — MCP/CLI boundary (stateless reads vs process operations)
- ADR-0003 — No backwards-compat shims
- #768 — QA Mode (magic-link persona login)
- `docs/reference/fitness-methodology.md` — Agent-Led Fitness Methodology
- `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` — current subprocess owner (to be refactored)

---

## Goal

Make it possible to spin up a live Dazzle example app — real Postgres, real Redis, real QA mode — from Python, CLI, MCP, or an autonomous loop, so the fitness engine's Phase B walkers can observe a real running app instead of `about:blank`.

Today, `dazzle.qa.server.connect_app` hardcodes `http://localhost:3000` / `http://localhost:8000` while `dazzle serve` assigns ports deterministically from a project-name hash (support_tickets is actually `:8981`/`:8969`). The existing path "works" only because the fitness strategy currently kills the subprocess before anyone notices the URL is wrong, or because the Playwright browser never actually loads the intended URL. That bug has to be closed as part of this work.

v1 ships **Mode A (developer one-shot) + the snapshot primitive**. Modes B, C, and D are specified here so the runner's knobs land in the right shape, but their CLI wrappers and mode-specific behaviours are follow-ups to be scoped based on real-world experience with Mode A.

---

## Non-goals

- Windows signal propagation support. The subprocess lifecycle code uses POSIX primitives (`os.setsid`, SIGTERM→SIGKILL escalation). Windows is a follow-up if anyone reports it.
- Baseline drift detection during long Mode C runs. Mode C isn't being built in v1.
- Log file garbage collection. v1 writes and never cleans. Add `dazzle e2e env logs --gc` in a follow-up once disk usage actually matters.
- Multi-tenant or multi-branch baselines. One baseline per `(project, alembic_rev, fixture_hash)` tuple; no branch awareness.
- Hot-reload for Mode C. Mode C isn't being built in v1.
- Remote Postgres — this design targets a single developer laptop with local Postgres, or a CI runner with an ephemeral Postgres container. Remote DBs work (pg_dump speaks TCP) but are untested.

---

## Mode Map

Four modes, one shared runner, different policy knobs:

| Mode | Purpose | DB policy | QA flags | Log output | Lifetime |
|------|---------|-----------|----------|------------|----------|
| **A** — dev one-shot | "I'm working on component X, run fitness against support_tickets once" | `preserve` (default) / `fresh` | auto-set when `personas=[...]` | captured → `.dazzle/e2e-logs/mode_a-<ts>.log`; last 50 lines dumped to stderr on failure | single run, teardown after |
| **B** — CI gate | "PR check runs fitness against all example apps on every push" | `restore` (hash-tagged baseline, lazy-built on first run) | always on | captured + archived as CI artefact | single run per target, teardown after |
| **C** — long-running dev | "Keep support_tickets running so I can browse it and hot-reload templates" | `preserve` | off by default (explicit opt-in) | streams to parent stdout/stderr | stays up until `dazzle e2e env stop` |
| **D** — autonomous loop | "Tick every N min: restore baseline, run fitness against the highest-priority row, report" | `restore` | always on | captured, tail on finding | per-tick launch+teardown, no persistent state |

**Mode catalogue is first-class data.** `src/dazzle/e2e/modes.py` exports `MODE_REGISTRY: tuple[ModeSpec, ...]` where `ModeSpec` has `name`, `description`, `db_policy`, `qa_flag_policy`, `log_output`, `lifetime`, `intended_use`. The MCP tool `mcp__dazzle__e2e` operation `list_modes` reads this registry directly — agents calling "what modes can I run?" get the source of truth, not a hardcoded string.

v1 ships only `mode_a` in the registry. Adding Mode B/C/D is a ~40-line append plus CLI wiring plus targeted tests — the runner itself already accommodates their policy knobs.

---

## Architecture

Four layers, bottom-up:

```
┌─────────────────────────────────────────────────────────┐
│ Callers                                                 │
│  • run_fitness_strategy (fitness_strategy.py, refactor) │
│  • dazzle e2e env start (cli/e2e/env.py)                │
│  • mcp__dazzle__e2e (mcp/server/handlers/e2e.py)        │
└────────────────────┬────────────────────────────────────┘
                     │ Runner API (Python)
┌────────────────────▼────────────────────────────────────┐
│ src/dazzle/e2e/ (NEW primitive package)                 │
│                                                         │
│  runner.py    — ModeRunner async context manager        │
│  modes.py     — ModeSpec + MODE_REGISTRY                │
│  lifecycle.py — PID lock + signal handlers + log tail   │
│  snapshot.py  — db snapshot/restore wrapper             │
│  baseline.py  — baseline compute + lazy build           │
│  errors.py    — E2EError hierarchy                      │
└────────────────────┬────────────────────────────────────┘
                     │ subprocess
┌────────────────────▼────────────────────────────────────┐
│ dazzle serve (existing, unchanged)                      │
│  • Auto-loads <project>/.env                            │
│  • Deterministic port hash                              │
│  • Writes .dazzle/runtime.json                          │
└─────────────────────────────────────────────────────────┘
```

### Package layout

**New primitive package** — `src/dazzle/e2e/`:
- `runner.py` — `ModeRunner` async context manager (launch → `AppConnection` → teardown).
- `modes.py` — `ModeSpec` dataclass, `MODE_REGISTRY`, `get_mode(name) -> ModeSpec`.
- `lifecycle.py` — `LockFile` (PID-based with 15-min TTL safety net), atexit + signal handler registration, log file creation.
- `snapshot.py` — `Snapshotter` (pg_dump/pg_restore wrapper).
- `baseline.py` — `BaselineManager`, `BaselineKey` (alembic rev + fixture hash).
- `errors.py` — `E2EError` hierarchy.

**CLI package split** — `src/dazzle/cli/e2e.py` (745 lines) → package:
- `src/dazzle/cli/e2e/__init__.py` — all 11 existing commands, unchanged.
- `src/dazzle/cli/e2e/env.py` — new `env` sub-typer with `start`, `status`, `stop`, `logs` commands.
- Registered via `e2e_app.add_typer(env_app, name="env")`.

**New MCP handler** — `src/dazzle/mcp/server/handlers/e2e.py`:
- Registered in `handlers_consolidated.py` and `tools_consolidated.py` alongside the other 26 tools.
- Read-only per ADR-0002.

**Fitness strategy refactor** — `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py`:
- `run_fitness_strategy(connection: AppConnection, ..., personas)` takes an already-running `AppConnection` — the runner owns subprocess lifecycle.
- Callers that want the old "launch and run" shape wrap it: `async with ModeRunner(...) as conn: await run_fitness_strategy(conn, ...)`.

**Deleted code** — per ADR-0003 (no shims):
- `dazzle.qa.server.connect_app` — replaced by `AppConnection.from_runtime_file(project_root)` helper on the `AppConnection` dataclass, which reads `.dazzle/runtime.json`. Callers are updated in the same commit.
- `dazzle.qa.server._start_app` — subsumed by `ModeRunner`.
- The hardcoded `:3000`/`:8000` path is the bug we're fixing, not preserving.

### Module contracts

#### `runner.ModeRunner`

Async context manager. Signature:

```python
class ModeRunner:
    def __init__(
        self,
        mode_spec: ModeSpec,
        project_root: Path,
        *,
        db_policy: Literal["preserve", "fresh", "restore"] | None = None,
        personas: list[str] | None = None,
        fresh: bool = False,  # alias for --fresh flag path
    ) -> None: ...

    async def __aenter__(self) -> AppConnection: ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
```

On enter:
1. Acquire `LockFile` at `<project_root>/.dazzle/mode_a.lock`.
2. Apply DB policy (preserve: no-op; fresh: reset+upgrade+demo; restore: `BaselineManager.restore()`).
3. Prepare env (os.environ copy + QA flags if personas non-empty).
4. Launch `python -m dazzle serve --local` as subprocess in a new process group, stdout+stderr → log file.
5. Register cleanup handlers (atexit + SIGINT + SIGTERM) **before** the first await after Popen.
6. Poll `<project_root>/.dazzle/runtime.json` (10s budget, 0.2s interval).
7. Parse runtime.json → `AppConnection(ui_url, api_url, process=proc)`.
8. Poll `{api_url}/docs` for 200 (30s budget) via existing `dazzle.qa.server.wait_for_ready`.
9. Return the connection.

On exit:
1. If `exc is not None`, read log file, print last 50 lines to stderr prefixed `[mode-a] subprocess output tail:`.
2. `proc.terminate()`; wait 5s; `proc.kill()` if still alive.
3. Close log file handle.
4. Release lock file (delete).
5. If teardown itself raises, log to stderr but do not raise — do not mask caller exceptions.

#### `modes.ModeSpec`

```python
@dataclass(frozen=True)
class ModeSpec:
    name: Literal["a", "b", "c", "d"]
    description: str
    db_policy_default: Literal["preserve", "fresh", "restore"]
    db_policies_allowed: frozenset[str]
    qa_flag_policy: Literal["auto_if_personas", "always_on", "always_off"]
    log_output: Literal["captured_tail_on_fail", "stream_live", "captured_archive"]
    lifetime: Literal["single_run", "long_running"]
    intended_use: str

MODE_REGISTRY: tuple[ModeSpec, ...] = (
    ModeSpec(
        name="a",
        description="Developer one-shot — launch an example app, yield connection, tear down.",
        db_policy_default="preserve",
        db_policies_allowed=frozenset({"preserve", "fresh", "restore"}),
        qa_flag_policy="auto_if_personas",
        log_output="captured_tail_on_fail",
        lifetime="single_run",
        intended_use="Running /ux-cycle Phase B locally against a specific component, "
                     "or invoking the fitness engine interactively from the CLI.",
    ),
)

def get_mode(name: str) -> ModeSpec: ...  # raises UnknownModeError on miss
```

#### `lifecycle.LockFile`

```python
class LockFile:
    def __init__(self, path: Path, *, ttl_seconds: int = 900) -> None: ...
    def acquire(self, mode_name: str, log_path: Path) -> None:
        """Acquire the lock. Writes {pid, mode, started_at, log_file}.
        Raises ModeAlreadyRunningError if a live PID holds the lock and the
        lock is less than `ttl_seconds` old. Stale locks (dead PID OR older
        than TTL) are silently deleted and re-acquired.
        """
    def release(self) -> None:
        """Delete the lock file. No-op if already gone. Does not raise."""
```

#### `snapshot.Snapshotter`

```python
class Snapshotter:
    def __init__(self) -> None:
        """Probes PATH for pg_dump and pg_restore.
        Raises PgDumpNotInstalledError if either is missing.
        """

    def capture(self, db_url: str, dest: Path) -> None:
        """pg_dump -Fc -Z 9 --no-owner --no-privileges <db_url> > <dest>.
        Writes to <dest>.tmp and os.rename on success (atomic).
        Raises SnapshotError on non-zero exit.
        """

    def restore(self, src: Path, db_url: str) -> None:
        """pg_restore --clean --if-exists --no-owner --no-privileges
        --dbname=<db_url> < <src>.
        Raises BaselineRestoreError on non-zero exit.
        """
```

#### `baseline.BaselineManager`

```python
@dataclass(frozen=True)
class BaselineKey:
    alembic_rev: str
    fixture_hash: str  # SHA-256 hex

    @property
    def fixture_hash_prefix(self) -> str:
        return self.fixture_hash[:12]

    def filename(self) -> str:
        return f"baseline-{self.alembic_rev}-{self.fixture_hash_prefix}.sql.gz"

class BaselineManager:
    def __init__(self, project_root: Path, db_url: str) -> None: ...

    def current_key(self) -> BaselineKey:
        """Compute (alembic_head, SHA-256 over demo fixture files).
        Raises BaselineKeyError if Alembic config missing.
        If no fixture files exist, fixture_hash is SHA-256 of literal 'no-fixture'.
        """

    def path_for(self, key: BaselineKey) -> Path:
        return self.project_root / ".dazzle" / "baselines" / key.filename()

    def ensure(self, *, fresh: bool = False) -> Path:
        """Returns path to a baseline file matching current_key().
        Lazy-builds if missing or fresh=True.
        """

    def restore(self) -> Path:
        """Ensure + Snapshotter.restore. Returns the path used."""

    def _build(self, dest: Path) -> None:
        """Lazy build pipeline — subprocess-calls the existing CLIs:
        1. dazzle db reset
        2. dazzle db upgrade
        3. dazzle demo generate  (skipped if no demo config)
        4. Snapshotter.capture(db_url, dest)
        Each step raises BaselineBuildError on failure, with stderr captured.
        """

    def gc(self, keep: int = 3) -> list[Path]:
        """Delete all baseline files for this project except the `keep` newest.
        Returns deleted paths.
        """
```

#### `errors.E2EError` hierarchy

```python
class E2EError(DazzleError): pass

# Runner-level
class ModeAlreadyRunningError(E2EError): pass
class UnknownModeError(E2EError): pass
class ModeLaunchError(E2EError): pass
class RuntimeFileTimeoutError(E2EError): pass
class HealthCheckTimeoutError(E2EError): pass
class RunnerTeardownError(E2EError): pass

# Snapshot-level
class SnapshotError(E2EError): pass
class PgDumpNotInstalledError(SnapshotError): pass
class BaselineKeyError(SnapshotError): pass
class BaselineBuildError(SnapshotError): pass
class BaselineRestoreError(SnapshotError): pass
```

All inherit from `DazzleError` so they get consistent CLI rendering.

Caller exceptions (fitness walker crashes, etc.) **propagate unchanged** — the runner does not wrap them in `E2EError`. Teardown-layer failures are logged to stderr but never shadow caller exceptions.

---

## Data Flow: Mode A Happy Path

Concrete trace — `run_fitness_strategy` against `support_tickets` with `personas=["admin", "customer"]`:

```
Caller (e.g., /ux-cycle Phase B):
    mode_spec = get_mode("a")
    project_root = repo_root / "examples" / "support_tickets"
    contract_path = ~/.claude/skills/ux-architect/components/data-table.md

    async with ModeRunner(
        mode_spec=mode_spec,
        project_root=project_root,
        db_policy="preserve",   # Mode A default
        personas=["admin", "customer"],
    ) as conn:

        # ──────── __aenter__ ────────

        # 1. Lock acquired (examples/support_tickets/.dazzle/mode_a.lock)
        #    If alive PID holds it → ModeAlreadyRunningError
        #    If stale → delete + acquire

        # 2. DB policy = preserve → no-op
        #    (restore would: ensure baseline file for current (rev, hash),
        #     lazy-build if missing, pg_restore from file)
        #    (fresh would: reset + upgrade + demo, no capture)

        # 3. Env prep:
        #    env = dict(os.environ)
        #    env["DAZZLE_ENV"] = "development"
        #    env["DAZZLE_QA_MODE"] = "1"   # personas non-empty → auto-set

        # 4. Launch subprocess in new process group:
        #    log_path = .dazzle/e2e-logs/mode_a-<iso_ts>.log
        #    proc = Popen(
        #        [sys.executable, "-m", "dazzle", "serve", "--local"],
        #        cwd=project_root, env=env,
        #        stdout=log_fh, stderr=STDOUT,
        #        preexec_fn=os.setsid,  # POSIX: new process group
        #    )
        #    register_atexit_cleanup(proc, lock)
        #    install_signal_handlers(SIGINT, SIGTERM)

        # 5. Poll .dazzle/runtime.json (10s budget, 0.2s interval)
        #    On appearance → parse → AppConnection(ui_url, api_url, process=proc)
        #    On timeout → proc.terminate(); tail log; raise RuntimeFileTimeoutError

        # 6. Poll {api_url}/docs for 200 (30s budget)
        #    On success → return conn
        #    On timeout → proc.terminate(); tail log; raise HealthCheckTimeoutError

        # Caller body runs:
        outcome = await run_fitness_strategy(
            conn,
            component_contract_path=contract_path,
            personas=["admin", "customer"],
        )

        # ──────── __aexit__ (on any path) ────────

        # a. If exc: read log file, print last 50 lines to stderr
        # b. proc.terminate(); proc.wait(timeout=5); proc.kill() on timeout
        # c. log_fh.close()
        # d. lock.release()
        # e. If any step raised: log to stderr, do not propagate
        #    (caller exception, if any, is what propagates)
```

### Key invariants

1. **Lock is acquired before any side effect.** Second Mode A against the same example bails before launching a subprocess.
2. **Subprocess is registered with cleanup handlers before the first await after Popen.** No window for Ctrl+C to orphan the child.
3. **`runtime.json` is the handshake signal.** We don't guess ports, we don't probe ports, we wait for the file `dazzle serve` writes. Wrong URLs in that file = upstream bug, fail loudly.
4. **Log tail is only surfaced on failure.** Success path is silent; failure path dumps enough to diagnose.
5. **Env precedence matches `dazzle serve`'s existing rule**: shell > `.env`. Because `_load_dotenv` only sets vars not already in `os.environ`, subprocess env vars set by the runner (`DAZZLE_QA_MODE=1`) override any `.env` file.
6. **Even worst-case Mode A self-heals within 15 minutes** — lock TTL catches orphaned locks.

---

## DB State Policy

Per-mode policy over a shared snapshot primitive. v1 implements all three policies (the primitive supports them all); only Mode A uses them.

| Policy | Mode A | Mode B | Mode C | Mode D |
|--------|--------|--------|--------|--------|
| `preserve` | default | — | always | — |
| `fresh` | via `--fresh` flag | — | — | — |
| `restore` | via `--db-policy=restore` | always | — | always |

### `preserve`
No-op. User owns DB state. Fast but runs are not reproducible run-to-run.

### `fresh`
`dazzle db reset → dazzle db upgrade → dazzle demo generate`. Slow (~15s) but deterministic. No snapshot file involved.

### `restore`
`BaselineManager.restore()`:
1. Compute `current_key = (alembic_head, sha256(fixture_files))`.
2. Look up `examples/<app>/.dazzle/baselines/baseline-{rev}-{hash12}.sql.gz`.
3. If missing: lazy-build via `fresh` pipeline + `pg_dump` to the file.
4. `pg_restore --clean` from the file.

Typical second-run cost: ~1–2s on support_tickets. First run pays the `fresh` cost + dump overhead.

### Baseline invariants

- **Hash covers `(alembic_rev, fixture_hash_prefix12)`** — two runs with the same schema + fixtures find the same file. Schema changes → new file lazy-built on next run. Old files sit until `gc` is called.
- **`baselines/` directory is gitignored** — dumps are never committed.
- **Hard-require `pg_dump`/`pg_restore`**. No soft fallback. `Snapshotter.__init__` probes PATH and raises `PgDumpNotInstalledError` with a `brew install postgresql@16` / `apt-get install postgresql-client-16` hint.
- **Atomic writes** — `_build` writes to `<filename>.tmp`, `os.rename` on success. Partial files never adopt the canonical name.
- **No automatic GC** — `dazzle db snapshot gc` is an explicit CLI command.

### Shared CLI primitives

Two new commands on the existing `dazzle db` typer:

```
dazzle db snapshot <name> [--db-url URL] [--project PATH]
dazzle db restore  <name> [--db-url URL] [--project PATH]
dazzle db snapshot gc [--keep N] [--project PATH]
```

Power users can snapshot/restore by hand. Mode A uses the Python API directly.

---

## QA Flags

Persona login requires `DAZZLE_ENV=development` + `DAZZLE_QA_MODE=1`. Policy:

- **Primary rule:** auto-set both when `personas=` is non-empty.
- **Fallback by mode:** Mode A/B/D default to set, Mode C defaults to unset (so demos aren't polluted by the QA Personas panel).

Implementation: `ModeRunner.__aenter__` sets env vars on the subprocess `env` dict before `Popen`. Because `dazzle serve`'s `_load_dotenv` only sets vars not already in `os.environ`, these subprocess-level vars win over anything in the project's `.env` file.

**User override**: anyone who wants Mode C with QA panel visible just passes `personas=[...]` or exports the vars in their shell before running.

---

## Ports

**No port management in Mode A.** The runner reads `<project_root>/.dazzle/runtime.json` after launch, which `dazzle serve` writes with the deterministic-per-project port pair. `AppConnection(ui_url, api_url)` comes straight from that file.

Consequences:
- support_tickets → `http://localhost:8981` / `http://localhost:8969` (its hashed pair).
- Different examples → different port pairs → run in parallel without collision.
- Two Mode A runs against the *same* example → second blocked by lock file.
- `--port`/`--api-port` overrides on `dazzle serve` still work — Mode A passes them through transparently if the caller wants.

---

## Env File Handling

**`dazzle serve` already handles `.env` loading** (`src/dazzle/cli/runtime_impl/serve.py::_load_dotenv`). Mode A does not reimplement this.

Expected developer workflow:
1. User creates `examples/<app>/.env` with at least `DATABASE_URL`, `REDIS_URL`.
2. `dazzle serve --local` (launched by Mode A) reads it automatically.
3. Shell env takes precedence for any var already set.

v1 ships a single `examples/support_tickets/.env.example` file with documented defaults:

```bash
# Local dev Postgres + Redis
DATABASE_URL=postgresql://localhost:5432/support_tickets_dev
REDIS_URL=redis://localhost:6379/0

# Optional: leave these unset to let Mode A auto-set them when personas are used.
# DAZZLE_ENV=development
# DAZZLE_QA_MODE=1
```

Users copy `.env.example` → `.env` and edit. `.env` is gitignored; `.env.example` is committed.

---

## Lifecycle, Locks, Log Tail

### Lock model

PID lock file at `examples/<app>/.dazzle/mode_a.lock` with contents:

```json
{
  "pid": 12345,
  "mode": "a",
  "started_at": "2026-04-14T10:12:34Z",
  "log_file": "/path/to/.dazzle/e2e-logs/mode_a-20260414T101234Z.log"
}
```

Acquisition logic:
- Lock file absent → create + acquire.
- Lock file present, PID alive (`os.kill(pid, 0)` succeeds), age < 15 min → raise `ModeAlreadyRunningError`.
- Lock file present, PID dead (`os.kill` raises `ProcessLookupError`) → stale, delete + acquire.
- Lock file present, age ≥ 15 min (regardless of PID state) → stale, delete + acquire.

Release: unconditional file delete, no-op if absent.

### Cleanup

Three mechanisms layered:
1. **`atexit`** handler registered when subprocess starts — best-effort cleanup on normal exit.
2. **SIGINT + SIGTERM handlers** — cleanup on Ctrl+C or external kill.
3. **15-min lock TTL** — safety net for SIGKILL and other cases where handlers don't run.

Normal path: `async with` exit → `__aexit__` terminates subprocess, releases lock, handlers fire as no-op.
Ctrl+C path: signal handler terminates subprocess, releases lock, raises `KeyboardInterrupt` for the caller.
SIGKILL path: nothing runs; next Mode A run within 15 min sees alive-or-dead PID check, deletes + proceeds.

### Log output (Mode A)

- Subprocess stdout+stderr both redirected to `examples/<app>/.dazzle/e2e-logs/mode_a-<iso_ts>.log`.
- `.dazzle/e2e-logs/` directory auto-created if missing.
- On successful exit: log file stays; nothing printed.
- On exception (caller or runner): last 50 lines printed to stderr, prefixed `[mode-a] subprocess output tail:`.

No automatic GC of log files in v1.

---

## Error Handling

**Policy:** runner-level errors raise `E2EError` subclasses; caller errors propagate unchanged; teardown failures are logged, never raised.

| Stage | Failure | Exception | CLI exit | Log tail printed? | State left |
|-------|---------|-----------|----------|-------------------|------------|
| Preflight | Alive PID in lock | `ModeAlreadyRunningError` | 2 | — | Lock untouched |
| Preflight | `pg_dump` missing (restore policy) | `PgDumpNotInstalledError` | 2 | — | Nothing created |
| Preflight | Alembic config missing (restore policy) | `BaselineKeyError` | 2 | — | Nothing created |
| Baseline | Build step crashed | `BaselineBuildError` (wraps underlying CLI error) | 2 | — | `.tmp` file may exist, never canonical — next run rebuilds |
| Baseline | `pg_restore` exit non-zero | `BaselineRestoreError` | 2 | — | DB may be partially restored — documented footgun; follow-up cleanup flag |
| Launch | `Popen` raised | `ModeLaunchError` | 2 | — | Lock released |
| Launch | `runtime.json` not in 10s | `RuntimeFileTimeoutError` | 2 | **yes** | Subprocess terminated, lock released |
| Launch | `/docs` not 200 in 30s | `HealthCheckTimeoutError` | 2 | **yes** | Subprocess terminated, lock released |
| Running | Caller body raised | propagates unchanged | N/A | **yes** | Subprocess terminated, lock released |
| Teardown | proc.terminate/kill/lock release failed | logged to stderr, **not raised** | N/A | — | Possible orphan; 15-min TTL catches |

### Key decisions

1. **No retries.** If runtime.json doesn't appear in 10s, the runner does not wait another 10s. Retries hide systemic problems. Fail fast; caller re-invokes if appropriate.
2. **Teardown errors never mask caller errors.** `__aexit__` reraises the caller's exception if any; its own failures go to stderr log only.
3. **No exception wrapping for caller errors.** Fitness walker crashes propagate with their original type. Agents and tests can catch `FitnessError` or `E2EError` as appropriate.
4. **Partial baseline state is recoverable by design** via atomic rename.
5. **Lock always released on exit**, even on teardown failure. 15-min TTL is the backstop.

---

## MCP Surface

**Tool name:** `mcp__dazzle__e2e`
**Read-only** per ADR-0002. Start/stop operations live in CLI only.

### Operations

```
list_modes() -> list[ModeDescriptor]
    Returns MODE_REGISTRY contents as JSON. v1: one entry (mode_a).

describe_mode(name: str) -> ModeDescriptor
    Single mode. Raises UnknownModeError on miss.

status(project_root: str | None = None) -> StatusReport
    Current runner state without mutation:
    {
      "lock_file": <path or null>,
      "lock_holder_pid": <int or null>,
      "lock_holder_alive": <bool>,
      "lock_age_seconds": <int or null>,
      "runtime_file": <path or null>,
      "runtime_ports": {"ui": int, "api": int} or null,
      "last_log_file": <path or null>,
      "last_log_tail": [<last 20 lines>] or null
    }
    If project_root is None: scans all examples/* and returns a list.

list_baselines(project_root: str) -> list[BaselineRecord]
    [
      {
        "filename": "baseline-abc123-def456789012.sql.gz",
        "alembic_rev": "abc123",
        "fixture_hash_prefix": "def456789012",
        "size_bytes": 834521,
        "mtime": "2026-04-14T15:12:34Z",
        "is_current": True
      }
    ]
    "is_current" indicates the file matching the current (rev, hash) tuple.
```

### Deliberately not in MCP

- `start`, `stop`, `restart` — CLI-only per ADR-0002.
- `build_baseline`, `snapshot`, `restore` — CLI-only.
- `tail_logs` streaming — static last-20-lines in `status` is the substitute.
- `run_fitness` shortcut — fitness is invoked by the caller, not MCP.

### Agent cognition flow

An agent asked "run fitness against support_tickets" walks:
1. `list_modes()` → sees Mode A with its `intended_use` description.
2. `status(project_root="examples/support_tickets")` → checks for in-progress run.
3. `list_baselines(...)` → knows whether `restore` will hit cache.
4. Invokes CLI (`dazzle e2e env start --mode=a support_tickets`) or Python API (test harness).

Mirrors the existing `discovery` tool + `dazzle discovery run` CLI split.

---

## CLI Surface

New commands under `dazzle e2e env`:

```
dazzle e2e env start <example> [--mode=a] [--fresh] [--personas=a,b,c]
                                [--db-policy=preserve|fresh|restore]
    Launches Mode A. Foreground — prints startup banner, blocks until Ctrl+C
    or subprocess exits. On exception, prints log tail to stderr.
    Primarily used by humans and "launch-and-observe" test scripts.

dazzle e2e env status [<example>]
    Prints MCP-equivalent status info as a table. No <example> = scan all.

dazzle e2e env stop <example>
    Reads lock file, SIGTERM to held PID, wait 5s, SIGKILL if alive, delete
    lock. No-op if no lock exists. For cleanup after crashes.

dazzle e2e env logs <example> [--tail N]
    Prints last N lines (default 50) of the most recent mode_a-*.log.
```

v1 implements all four. `start` is the workhorse; `status`/`stop`/`logs` are operational necessities.

**Note on `start` blocking behaviour:** `start` is synchronous-feeling from the CLI but the Runner is async — the CLI wraps `asyncio.run(...)` around an infinite-sleep body inside the `async with`, and catches `KeyboardInterrupt` for clean shutdown. Agents that want "launch, wait for ready, return control" should use the Python API, not the CLI.

---

## Fitness Strategy Refactor

Current (v1.0.3):

```python
async def run_fitness_strategy(
    example_app: str,
    project_root: Path,
    component_contract_path: Path | None = None,
    personas: list[str] | None = None,
) -> StrategyOutcome:
    # Owns subprocess launch via connect_app (with hardcoded-port bug)
    # Owns Playwright bundle
    # Owns per-persona login + walk
    ...
```

New:

```python
async def run_fitness_strategy(
    connection: AppConnection,           # ← caller provides; runner-owned
    *,
    project_root: Path,                  # still needed for ledger path
    component_contract_path: Path | None = None,
    personas: list[str] | None = None,
) -> StrategyOutcome:
    # Owns Playwright bundle
    # Owns per-persona login + walk
    # Does NOT own subprocess lifecycle
    ...
```

Callers migrate as:

```python
# Before:
outcome = await run_fitness_strategy(
    example_app="support_tickets",
    project_root=Path("/Volumes/SSD/Dazzle"),
    component_contract_path=contract_path,
    personas=["admin"],
)

# After:
async with ModeRunner(
    mode_spec=get_mode("a"),
    project_root=repo_root / "examples" / "support_tickets",
    personas=["admin"],
) as conn:
    outcome = await run_fitness_strategy(
        conn,
        project_root=repo_root / "examples" / "support_tickets",
        component_contract_path=contract_path,
        personas=["admin"],
    )
```

Breaking change — no shim. All callers updated in the same commit.

---

## Testing Strategy

Three layers. Each layer covers failure modes the other layers can't.

### Layer 1 — Unit tests (no real Postgres, no real subprocess)

Location: `tests/unit/e2e/`

**`test_modes.py`**
- `MODE_REGISTRY` has exactly one entry (`mode_a`) in v1.
- `get_mode("a")` returns `ModeSpec` with expected fields.
- `get_mode("b")` raises `UnknownModeError`.
- `ModeSpec` is frozen (immutable).

**`test_lifecycle.py`**
- `LockFile.acquire` on empty dir → creates file with current PID.
- `LockFile.acquire` when alive PID holds lock → raises `ModeAlreadyRunningError`. Monkeypatches `os.kill(pid, 0)` to succeed.
- `LockFile.acquire` when dead PID holds lock → deletes + acquires. Monkeypatches `os.kill` to raise `ProcessLookupError`.
- `LockFile.acquire` when lock is >15min old, PID alive → deletes + acquires (TTL safety net).
- `LockFile.release` deletes; no-op if already gone; does not raise.

**`test_snapshot.py`**
- `Snapshotter.__init__` probes PATH via `shutil.which`; missing either binary → `PgDumpNotInstalledError`.
- `Snapshotter.capture` builds `pg_dump -Fc -Z 9 --no-owner --no-privileges ...` argv. Uses recorded `subprocess.run` mock.
- `Snapshotter.restore` builds `pg_restore --clean --if-exists --no-owner --no-privileges --dbname=... ...` argv.
- Non-zero subprocess exit → `SnapshotError` with captured stderr in the message.
- Atomic write: `capture` writes to `<dest>.tmp` then `os.rename` to `<dest>`; failed capture leaves no file at `<dest>`.

**`test_baseline.py`**
- `BaselineKey.filename` produces `baseline-<rev>-<hash12>.sql.gz`.
- `current_key` combines Alembic head + fixture SHA. Monkeypatches `alembic.script.ScriptDirectory` + hashes a known temp fixture dir.
- `current_key` with no fixtures → uses `sha256("no-fixture")` as fixture hash.
- `path_for` returns `<project>/.dazzle/baselines/<filename>`.
- `ensure(fresh=False)` no-ops when file exists.
- `ensure(fresh=True)` always rebuilds via mocked `_build`.
- `ensure` on missing file calls `_build` once.
- `_build` invokes `reset → upgrade → demo → capture` in order (call recorder).
- Failure in step 2 leaves no canonical file at dest.
- `gc(keep=N)` preserves the N newest baseline files, deletes older.

**`test_runner.py`**
- Happy path: lock acquired, (no baseline for preserve), `Popen` called with expected argv, runtime.json poll returns known file, health check returns True, `AppConnection` yielded. Uses `asyncio` test harness + injected fakes.
- `runtime.json` timeout → fake subprocess terminated, `RuntimeFileTimeoutError` raised with log tail.
- Health check timeout → same path, `HealthCheckTimeoutError`.
- Caller body raises → fake subprocess terminated, log tail printed to stderr (via `capsys`), lock released, caller exception propagates unchanged.
- Teardown failure (lock release raises) → logged, does not raise.
- `personas=None` → `DAZZLE_QA_MODE` NOT in subprocess env.
- `personas=["admin"]` → `DAZZLE_ENV=development` and `DAZZLE_QA_MODE=1` in subprocess env.
- Shell env precedence: runner-set vars override values a fake `_load_dotenv` would try to set.

### Layer 2 — Integration tests (real Postgres, real subprocess, no Playwright)

Location: `tests/integration/e2e/test_mode_a_integration.py`
Gating: `@pytest.mark.integration` — skipped in default `pytest`, opt-in via `pytest -m integration`. Requires `DATABASE_URL` + `REDIS_URL` set + `pg_dump`/`pg_restore` on PATH + real running Postgres/Redis.

- **`test_mode_a_launch_and_teardown`** — launches support_tickets via Mode A with `preserve` policy. Asserts `AppConnection.ui_url` matches the deterministic hashed port, `requests.get(f"{api_url}/docs").status_code == 200`. After `async with` exit: lock file gone, `proc.poll() is not None`.
- **`test_mode_a_concurrent_same_example_raises`** — starts Mode A in background task, starts a second Mode A → second raises `ModeAlreadyRunningError`. First completes normally.
- **`test_mode_a_baseline_roundtrip`** — Mode A with `restore` on a fresh example. First run lazy-builds baseline (file exists at expected path). Second run restores in <3s. `gc(keep=1)` sweeps old baselines.
- **`test_mode_a_env_precedence`** — writes `.env` with `DATABASE_URL=postgresql://wrong`, sets shell `DATABASE_URL=postgresql://right`, launches Mode A, asserts the subprocess received the shell value.
- **`test_mode_a_stale_lock_recovery`** — writes stale lock file with dead PID → Mode A deletes and proceeds.

### Layer 3 — E2E test against real fitness strategy

Location: `tests/e2e/fitness/test_support_tickets_fitness.py` (existing — extend, don't add).
Gating: existing `@pytest.mark.e2e`, opt-in via `pytest -m e2e`.

- **Rewrite** `test_support_tickets_fitness_cycle_completes` to use `ModeRunner` explicitly instead of the old `run_fitness_strategy` subprocess launch.
- **Rewrite** `test_support_tickets_multi_persona_cycle_completes` to use `ModeRunner` with `personas=["admin", "customer", "agent", "manager"]`.
- **New** `test_support_tickets_baseline_restore_idempotent`: Mode A with `restore`, run twice. Assert second run >10× faster than first. Assert DB byte-identical (compare `pg_dump` output of a known table).

These must actually invoke a real Dazzle subprocess against a real Postgres. That's the whole point.

### Pass criteria

- All three layers green.
- `tests/e2e/fitness/test_support_tickets_fitness.py` runs end-to-end against a clean checkout with `DATABASE_URL` + `REDIS_URL` set and `postgresql@16` installed.

### Deliberately out of scope

- Windows signal propagation (no Windows CI).
- Concurrent Mode A runs against *different* examples (happy path by construction).
- `pg_restore --clean` on a DB with extra tables not in the dump.
- Mode C long-running "hot reload mid-session" behaviour (Mode C not built in v1).
- MCP handler tests against a real MCP client (handlers are unit-testable via consolidated dispatch).

---

## Implementation Order

Suggested sequence for the writing-plans pass:

1. **`errors.py`** — empty-shell exception hierarchy (used by everything downstream).
2. **`snapshot.py` + unit tests** — depends only on `subprocess`, no other new modules.
3. **`baseline.py` + unit tests** — depends on `snapshot.py`.
4. **`lifecycle.py` + unit tests** — PID lock, no other dependencies.
5. **`modes.py` + unit tests** — data only.
6. **`runner.py` + unit tests** — depends on all of the above.
7. **`AppConnection.from_runtime_file` helper + delete old `connect_app`**.
8. **Fitness strategy refactor** (break API signature; update callers).
9. **CLI package split (`cli/e2e.py` → `cli/e2e/__init__.py`) — pure refactor.**
10. **New `cli/e2e/env.py` commands** — `start`, `status`, `stop`, `logs`.
11. **MCP handler `mcp/server/handlers/e2e.py`** + registration in consolidated tools.
12. **`examples/support_tickets/.env.example`** — documented defaults.
13. **Integration tests** — layer 2.
14. **E2E test rewrites** — layer 3.
15. **Docs** — `docs/reference/e2e-environment.md` (user reference for Mode A).

Each step commits independently; the fitness strategy refactor (step 8) is the biggest single change because it rewires every caller.

---

## Risks

1. **`pg_dump` / `pg_restore` on CI runners** — requires explicit install in the CI job. Non-Homebrew environments may only ship `libpq`. Mitigation: document in `.github/workflows/ci.yml` changes when that work lands.
2. **Baseline file invalidation via Alembic rebasing** — a squashed-migrations rebase changes `alembic_head` without changing fixture contents, orphaning existing baseline files. Mitigation: `dazzle db snapshot gc` exists; also documents the behaviour.
3. **Subprocess leak on SIGKILL** — if the parent Python is SIGKILLed, `atexit` and signal handlers don't run. Mitigation: 15-min lock TTL + active PID check + `os.setsid` process group (so orphans can be reaped via `pgrep -g <pgid>` in a future cleanup tool).
4. **runtime.json race** — `dazzle serve` writes runtime.json via the existing `ports.write_runtime_file`. Mode A reads it via normal filesystem polling. Race: writer has flushed name but not content. Mitigation: poll reads the file, catches `JSONDecodeError`, retries until valid or timeout. Write is atomic on POSIX (single `write` call).
5. **Baseline portability across machines** — `pg_dump -Fc` is mostly portable but extension-sensitive. If a project uses `pg_trgm` or `uuid-ossp`, the restore target DB must have them pre-installed. Mitigation: document; example apps avoid non-default extensions in v1.

---

## Open Questions Deferred to Implementation

These don't need brainstorm decisions — implementer judgment:

- Exact polling intervals for runtime.json and /docs (0.2s / 0.5s assumed).
- Whether `preexec_fn=os.setsid` belongs on all POSIX launches or only when we detect non-interactive callers.
- Log file naming — ISO timestamp vs UUID (ISO chosen above for human readability).
- Whether `dazzle e2e env start` should flock the log file for tailing from `logs` command.

---

## Summary

- **Mode A + snapshot primitive ship in v1**; Modes B/C/D sketched but not wired.
- **New `src/dazzle/e2e/` package** holds runner, modes, lifecycle, snapshot, baseline, errors.
- **`src/dazzle/cli/e2e.py` splits into a package** to host `env` subcommands without ballooning.
- **`dazzle.qa.server.connect_app` is deleted** and replaced by `AppConnection.from_runtime_file` — fixes a latent hardcoded-port bug.
- **Fitness strategy stops owning subprocess lifecycle** — it takes an `AppConnection` from the runner.
- **MCP gets read-only `mcp__dazzle__e2e`** tool for mode/status/baseline introspection.
- **DB snapshot/restore is a CLI primitive** usable independently of Mode A.
- **Hash-tagged, lazy-built baselines** at `examples/<app>/.dazzle/baselines/baseline-{rev}-{hash12}.sql.gz`.
- **Breaking changes land in the same commit** per ADR-0003 — no shims.
