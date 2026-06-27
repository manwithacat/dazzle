# DB-artifact Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single declarative registry of every framework database artifact (class / creator / boot-entry / owner / RLS posture / in-baseline / boot-DDL-gated), with an executable contract that asserts those invariants — collapsing the triplicated `IN_SCOPE_TABLES` list and catching the #1495 class (ungated boot-DDL) at test time.

**Architecture:** A pure-data module `src/dazzle/db/artifact_registry.py` is the source of truth. `framework_schema_snapshot.IN_SCOPE_TABLES` and the real-PG parity test derive their in-scope set from it. A static (no-DB) contract test asserts: every registered boot-entry self-gates with `skip_boot_schema_ddl()`; every framework function issuing app-DB `CREATE TABLE/INDEX` is registered (completeness sweep with an executable excluded-classes allowlist); RLS posture matches `rls_schema`. A `dazzle inspect db-artifacts` command + `docs/reference/db-artifacts.md` + ADR-0047 + an ADR-0044 amendment + a CLAUDE.md pointer are the agent-facing surfaces.

**Tech Stack:** Python 3.12+, `dataclasses` + `StrEnum`, `ast` (stdlib) for the static scans, Typer (`src/dazzle/cli/inspect.py` pattern), pytest. uv toolchain.

## Global Constraints

- **No new singletons** — registry is module-level immutable data, no mutable globals (ADR-0005; #1445 ratchet).
- **Layer direction** — the registry lives in `src/dazzle/db/`; it may import from `dazzle.core.*` only. It must NOT import `dazzle.http.*` (import-linter `core`/`db` below `http`). Creator/boot_entry references are **dotted strings**, resolved lazily in tests/commands — the registry never imports the http modules it names.
- **No `from __future__ import annotations` in FastAPI route files** (ADR-0014) — N/A here (registry/test/CLI are not route files; `from __future__ import annotations` is fine in them and is the repo norm).
- **Type hints required** on all public functions (mypy-enforced).
- **Bump on every fix** — `/bump patch` before each push; clean worktree after (CLAUDE.md ship discipline).
- **Pin exact values** — the 30 in-baseline table names are fixed (listed verbatim in Task 1); the contract proves the registry reproduces them.
- **CHANGELOG** — final task adds an `### Added` entry; api-surface/ir-types baselines unaffected (no public IR change).

---

### Task 1: The registry module

**Files:**
- Create: `src/dazzle/db/artifact_registry.py`
- Test: `tests/unit/test_artifact_registry.py`

**Interfaces:**
- Produces:
  - `class ArtifactClass(StrEnum)` — members `FRAMEWORK_INTERNAL`, `EVENT_BUS_TRANSPORT`, `OPS_DB`, `APP_ENTITY`, `TENANT_REGISTRY`
  - `class Ownership(StrEnum)` — `OWNER_ROLE`, `RUNTIME_SELF`, `N_A`
  - `class RlsPosture(StrEnum)` — `FENCED`, `NON_FENCED`, `NOT_APPLICABLE`
  - `@dataclass(frozen=True) class Artifact` — fields exactly: `name: str`, `cls: ArtifactClass`, `creator: str`, `boot_entry: str | None`, `owner: Ownership`, `rls: RlsPosture`, `in_baseline: bool`, `boot_ddl_gated: bool`, `notes: str = ""`, `is_pattern: bool = False`
  - `DB_ARTIFACTS: tuple[Artifact, ...]`
  - `def in_baseline_tables() -> frozenset[str]` — `frozenset(a.name for a in DB_ARTIFACTS if a.in_baseline and not a.is_pattern)`
  - `def framework_boot_entries() -> tuple[Artifact, ...]` — artifacts with a non-None `boot_entry`
  - `def concrete_creators() -> frozenset[str]` — every `creator` plus every non-None `boot_entry`, for non-pattern rows

- [ ] **Step 1: Write the failing test (registry reproduces the 30 in-scope names)**

```python
# tests/unit/test_artifact_registry.py
"""#1495 follow-on — the DB-artifact registry is the single source of truth.

`in_baseline_tables()` must reproduce exactly the 30 framework tables that
`ensure_framework_schema` creates (the ADR-0044 in-scope set). This pins the
collapse: framework_schema_snapshot.IN_SCOPE_TABLES becomes registry-derived.
"""

from __future__ import annotations

from dazzle.db.artifact_registry import (
    DB_ARTIFACTS,
    Artifact,
    ArtifactClass,
    in_baseline_tables,
)

# The 30 framework tables, verbatim from framework_schema_snapshot.IN_SCOPE_TABLES.
_EXPECTED_BASELINE = frozenset(
    {
        "_dazzle_params",
        "users", "sessions", "memberships", "organizations", "membership_events",
        "invitations", "connections", "connection_secret_events", "scim_groups",
        "scim_group_members", "saml_consumed_assertions", "password_reset_tokens",
        "magic_links", "email_verification_tokens", "user_preferences", "join_requests",
        "process_runs", "process_tasks",
        "_dazzle_audit_log", "_dazzle_atomic_audit", "dazzle_files", "refresh_tokens",
        "devices", "_grants", "_grant_events", "_dazzle_otp_codes",
        "_dazzle_recovery_codes", "_dazzle_event_inbox", "_dazzle_event_outbox",
    }
)


def test_in_baseline_tables_reproduces_the_in_scope_set() -> None:
    assert in_baseline_tables() == _EXPECTED_BASELINE


def test_every_artifact_is_well_formed() -> None:
    seen: set[str] = set()
    for a in DB_ARTIFACTS:
        assert isinstance(a, Artifact)
        # boot_ddl_gated implies an independent boot path to gate.
        if a.boot_ddl_gated:
            assert a.boot_entry is not None, f"{a.name}: gated but no boot_entry"
        # orchestrator-only rows declare no self-gate.
        if a.boot_entry is None and not a.is_pattern:
            assert a.boot_ddl_gated is False, f"{a.name}: no boot_entry yet gated"
        # exact (non-pattern) framework names are unique.
        if not a.is_pattern and a.cls is ArtifactClass.FRAMEWORK_INTERNAL:
            assert a.name not in seen, f"duplicate framework artifact {a.name}"
            seen.add(a.name)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_artifact_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.db.artifact_registry'`

- [ ] **Step 3: Write the registry module**

Create `src/dazzle/db/artifact_registry.py` with the enums, dataclass, `DB_ARTIFACTS`, and helpers. Use the data below verbatim. **Owner** = `OWNER_ROLE` for all FRAMEWORK_INTERNAL (split-ownership: `dazzle_owner` owns, runtime is non-owner), `RUNTIME_SELF` for EVENT_BUS_TRANSPORT and OPS_DB. **boot_entry** is set only for the six independent gated boot paths; everything else is orchestrator-only (`None`). **rls** is provisional `NON_FENCED` for framework tables and is *verified/corrected* in Step 4 against the generator.

```python
"""Single source of truth for every database artifact the framework manages.

Each artifact declares five orthogonal facts an agent would otherwise reconstruct
from scattered ADRs + code: class, creator (where the DDL lives), boot_entry (the
independent startup path that must self-gate, or None for orchestrator-only),
owner, RLS posture, baseline membership, and boot-DDL gating. The executable
contract in tests/unit/test_db_artifact_contract.py keeps these honest.

Reference: docs/reference/db-artifacts.md · ADR-0047 · ADR-0044 (baseline mechanism).

Layer note: this module is pure data — creator/boot_entry are DOTTED STRINGS,
resolved lazily by the contract test and the inspect command, so the registry
never imports the http.* modules it names (db/ stays below http/).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactClass(StrEnum):
    FRAMEWORK_INTERNAL = "framework_internal"   # in the ADR-0044 baseline; owner-created
    EVENT_BUS_TRANSPORT = "event_bus_transport"  # {prefix}* ; excluded; self-creating
    OPS_DB = "ops_db"                            # separate ops database; own lifecycle
    APP_ENTITY = "app_entity"                    # per-DSL; migration-engine generated
    TENANT_REGISTRY = "tenant_registry"          # public.tenants + per-tenant schemas


class Ownership(StrEnum):
    OWNER_ROLE = "owner_role"        # dazzle_owner owns; runtime serves as non-owner
    RUNTIME_SELF = "runtime_self"    # the creating connection owns what it makes
    N_A = "n_a"


class RlsPosture(StrEnum):
    FENCED = "fenced"                # ENABLE + FORCE ROW LEVEL SECURITY
    NON_FENCED = "non_fenced"        # no RLS today
    NOT_APPLICABLE = "not_applicable"  # separate DB / transport / per-tenant


@dataclass(frozen=True)
class Artifact:
    name: str
    cls: ArtifactClass
    creator: str
    boot_entry: str | None
    owner: Ownership
    rls: RlsPosture
    in_baseline: bool
    boot_ddl_gated: bool
    notes: str = ""
    is_pattern: bool = False


_AUTH_CREATOR = "dazzle.http.runtime.auth.store.ensure_auth_core_tables"
_AUTH_BOOT = "dazzle.http.runtime.auth.store.AuthStore._init_db"
_ORCH = "dazzle.http.runtime.framework_schema._ensure_framework_schema_ddl"

_AUTH_TABLES = (
    "users", "sessions", "memberships", "organizations", "membership_events",
    "invitations", "connections", "connection_secret_events", "scim_groups",
    "scim_group_members", "saml_consumed_assertions", "password_reset_tokens",
    "magic_links", "email_verification_tokens", "user_preferences", "join_requests",
)


def _fw(
    name: str,
    creator: str,
    *,
    boot_entry: str | None,
    rls: RlsPosture = RlsPosture.NON_FENCED,
    notes: str = "",
) -> Artifact:
    return Artifact(
        name=name,
        cls=ArtifactClass.FRAMEWORK_INTERNAL,
        creator=creator,
        boot_entry=boot_entry,
        owner=Ownership.OWNER_ROLE,
        rls=rls,
        in_baseline=True,
        boot_ddl_gated=boot_entry is not None,
        notes=notes,
    )


DB_ARTIFACTS: tuple[Artifact, ...] = (
    # ── framework internal (in the ADR-0044 baseline) ──────────────────────
    _fw("_dazzle_params", _ORCH, boot_entry=None, notes="orchestrator-only"),
    *[_fw(t, _AUTH_CREATOR, boot_entry=_AUTH_BOOT) for t in _AUTH_TABLES],
    _fw("process_runs", _ORCH, boot_entry="dazzle.core.process.pg_state.PgProcessStateStore._ensure"),
    _fw("process_tasks", _ORCH, boot_entry="dazzle.core.process.pg_state.PgProcessStateStore._ensure"),
    _fw("_dazzle_audit_log", "dazzle.http.runtime.audit_log.ensure_audit_log_table",
        boot_entry="dazzle.http.runtime.audit_log.AuditLogger._init_db"),
    _fw("_dazzle_atomic_audit", _ORCH, boot_entry=None, notes="orchestrator-only; lazy ensure in mutation path is no-op when table exists"),
    _fw("dazzle_files", "dazzle.http.runtime.file_storage.ensure_file_storage_tables",
        boot_entry="dazzle.http.runtime.file_storage.FileMetadataStore._init_db"),
    _fw("refresh_tokens", "dazzle.http.runtime.token_store.ensure_refresh_token_tables", boot_entry=None, notes="orchestrator-only (verify Step 4)"),
    _fw("devices", "dazzle.http.runtime.device_registry.ensure_device_tables", boot_entry=None, notes="orchestrator-only (verify Step 4)"),
    _fw("_grants", "dazzle.http.runtime.grant_store.ensure_grant_tables", boot_entry=None, notes="orchestrator-only (verify Step 4)"),
    _fw("_grant_events", "dazzle.http.runtime.grant_store.ensure_grant_tables", boot_entry=None, notes="orchestrator-only (verify Step 4)"),
    _fw("_dazzle_otp_codes", "dazzle.http.runtime.otp_store.ensure_otp_tables", boot_entry=None, notes="orchestrator-only (verify Step 4)"),
    _fw("_dazzle_recovery_codes", "dazzle.http.runtime.recovery_codes.ensure_recovery_code_tables", boot_entry=None, notes="orchestrator-only (verify Step 4)"),
    _fw("_dazzle_event_inbox", "dazzle.http.events.inbox.EventInbox.create_table",
        boot_entry="dazzle.http.events.inbox.EventInbox.create_table"),
    _fw("_dazzle_event_outbox", "dazzle.http.events.outbox.EventOutbox.create_table",
        boot_entry="dazzle.http.events.outbox.EventOutbox.create_table"),
    # ── event-bus transport (excluded; dynamic prefix; self-creating) ──────
    *[
        Artifact(
            name=n,
            cls=ArtifactClass.EVENT_BUS_TRANSPORT,
            creator="dazzle.http.events.postgres_bus.PostgresBus._create_tables",
            boot_entry=None,
            owner=Ownership.RUNTIME_SELF,
            rls=RlsPosture.NOT_APPLICABLE,
            in_baseline=False,
            boot_ddl_gated=False,
            notes="dynamic {prefix}; excluded from baseline",
            is_pattern=True,
        )
        for n in ("{prefix}events", "{prefix}consumer_offsets", "{prefix}dlq")
    ],
    # ── ops database (separate DB; own lifecycle) ──────────────────────────
    *[
        Artifact(
            name=n,
            cls=ArtifactClass.OPS_DB,
            creator="dazzle.http.runtime.ops_database.OpsDatabase._apply_migrations",
            boot_entry=None,
            owner=Ownership.RUNTIME_SELF,
            rls=RlsPosture.NOT_APPLICABLE,
            in_baseline=False,
            boot_ddl_gated=False,
            notes="separate ops_integration DB",
        )
        for n in ("ops_credentials", "health_checks", "api_calls", "analytics_events", "event_log", "retention_config")
    ],
    # ── dynamic classes (described, not enumerated) ────────────────────────
    Artifact(
        name="<app entities>",
        cls=ArtifactClass.APP_ENTITY,
        creator="dazzle.db.migration_engine.generate_revision",
        boot_entry=None,
        owner=Ownership.OWNER_ROLE,
        rls=RlsPosture.FENCED,
        in_baseline=False,
        boot_ddl_gated=False,
        notes="per-DSL; created by alembic migrations the engine generates; tenant-scoped entities are RLS-fenced",
        is_pattern=True,
    ),
    Artifact(
        name="public.tenants / <tenant schemas>",
        cls=ArtifactClass.TENANT_REGISTRY,
        creator="dazzle.http.runtime.tenant",
        boot_entry=None,
        owner=Ownership.OWNER_ROLE,
        rls=RlsPosture.NOT_APPLICABLE,
        in_baseline=False,
        boot_ddl_gated=False,
        notes="tenant registry + per-tenant schemas; separate lifecycle",
        is_pattern=True,
    ),
)


def in_baseline_tables() -> frozenset[str]:
    """THE single source of the in-scope framework table set (ADR-0044)."""
    return frozenset(a.name for a in DB_ARTIFACTS if a.in_baseline and not a.is_pattern)


def framework_boot_entries() -> tuple[Artifact, ...]:
    """Artifacts with an independent startup path that must self-gate."""
    return tuple(a for a in DB_ARTIFACTS if a.boot_entry is not None)


def concrete_creators() -> frozenset[str]:
    """Every concrete DDL-issuing dotted-ref the registry accounts for."""
    refs: set[str] = set()
    for a in DB_ARTIFACTS:
        refs.add(a.creator)
        if a.boot_entry is not None:
            refs.add(a.boot_entry)
    return frozenset(refs)
```

- [ ] **Step 4: Verify the provisional classifications, then re-run the test**

Verify the two provisional fields against reality (these are *verifications*, not guesses left in):

```bash
# (a) Confirm the five "orchestrator-only (verify Step 4)" stores have NO independent
#     ungated boot path. Each should have ZERO hits OR only the orchestrator caller:
uv run python - <<'PY'
import ast, pathlib
roots = ["token_store", "device_registry", "grant_store", "otp_store", "recovery_codes"]
for r in roots:
    p = pathlib.Path(f"src/dazzle/http/runtime/{r}.py")
    src = p.read_text()
    # A self-gating or self-calling boot path would call the ensure_* fn from a class _init_db.
    print(r, "calls skip_boot_schema_ddl:", "skip_boot_schema_ddl" in src,
          "| has _init_db:", "_init_db" in src)
PY
# Expected: skip_boot_schema_ddl False AND _init_db False for all five → they are
# orchestrator-only, boot_entry=None is correct. If any prints _init_db True, READ it:
# an ungated _init_db that calls ensure_* at boot is a latent #1495 sibling — STOP,
# set its boot_entry + gate it (separate fix), and note it.

# (b) Derive RLS posture: which framework tables get FORCE RLS from the generator.
uv run python - <<'PY'
from dazzle.http.runtime.rls_schema import build_all_rls_ddl  # adjust import if signature differs
# Build the framework-table RLS DDL the generator emits and print which carry FORCE.
# If build_all_rls_ddl requires an appspec, load a minimal one or inspect the
# fenced-table set it computes. Print the table names that appear with
# "FORCE ROW LEVEL SECURITY"; set rls=FENCED for those framework rows, else NON_FENCED.
print("Run: grep the generator output for 'FORCE ROW LEVEL SECURITY' table names")
PY
```

For any framework row the generator marks `FORCE`, change its `_fw(..., rls=RlsPosture.FENCED)`. Leave the rest `NON_FENCED`. (Known from #1495: `_dazzle_event_inbox`, `_dazzle_event_outbox`, `process_runs` are `NON_FENCED`.) Remove the `(verify Step 4)` note from any row you confirmed.

Run: `uv run pytest tests/unit/test_artifact_registry.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Lint, type, commit**

```bash
uv run ruff check src/dazzle/db/artifact_registry.py tests/unit/test_artifact_registry.py --fix
uv run ruff format src/dazzle/db/artifact_registry.py tests/unit/test_artifact_registry.py
uv run mypy src/dazzle/db/artifact_registry.py
git add src/dazzle/db/artifact_registry.py tests/unit/test_artifact_registry.py
git commit -m "feat(db): DB-artifact registry — declarative source of truth (#1495 follow-on)"
```

---

### Task 2: Collapse the triplicated IN_SCOPE_TABLES

**Files:**
- Modify: `src/dazzle/http/runtime/framework_schema_snapshot.py:53-89` (replace the literal frozenset with a registry-derived one)
- Modify: `tests/integration/test_framework_baseline_parity_pg.py:49-85` (import the registry helper instead of the local literal)
- Modify: `src/dazzle/http/runtime/framework_schema.py` (docstring: stop re-listing; point at the registry)
- Test: `tests/unit/test_in_scope_single_source.py`

**Interfaces:**
- Consumes: `dazzle.db.artifact_registry.in_baseline_tables` (Task 1)
- Produces: `framework_schema_snapshot.IN_SCOPE_TABLES` now `== in_baseline_tables()`

- [ ] **Step 1: Write the failing test (single source)**

```python
# tests/unit/test_in_scope_single_source.py
"""The in-scope framework table set has ONE source: the artifact registry.
framework_schema_snapshot.IN_SCOPE_TABLES and the parity test derive from it."""

from __future__ import annotations

from dazzle.db.artifact_registry import in_baseline_tables
from dazzle.http.runtime.framework_schema_snapshot import IN_SCOPE_TABLES


def test_snapshot_in_scope_is_registry_derived() -> None:
    assert IN_SCOPE_TABLES == in_baseline_tables()
    # identity-of-content: not a hand-copy that could drift
    assert set(IN_SCOPE_TABLES) == set(in_baseline_tables())
```

- [ ] **Step 2: Run to verify it passes already OR fails on drift**

Run: `uv run pytest tests/unit/test_in_scope_single_source.py -q`
Expected: PASS if the literals already match (they do today); this test is the *guard*. Proceed to make the source single regardless.

- [ ] **Step 3: Repoint the snapshot constant**

In `src/dazzle/http/runtime/framework_schema_snapshot.py`, replace the verbatim `IN_SCOPE_TABLES: frozenset[str] = frozenset({ ... 30 names ... })` block (lines ~53-89) with:

```python
from dazzle.db.artifact_registry import in_baseline_tables

# The in-scope framework table set is owned by the DB-artifact registry
# (ADR-0047). This module consumes it; it does not re-declare it.
IN_SCOPE_TABLES: frozenset[str] = in_baseline_tables()
```

(Keep the existing module behaviour — `regenerate_and_print()` and the snapshot dict are unchanged; only the table-name set is now derived.)

- [ ] **Step 4: Repoint the parity test**

In `tests/integration/test_framework_baseline_parity_pg.py`, replace its local `IN_SCOPE_TABLES: frozenset[str] = frozenset({ ... })` (lines ~49-85) with:

```python
from dazzle.db.artifact_registry import in_baseline_tables

IN_SCOPE_TABLES: frozenset[str] = in_baseline_tables()
```

- [ ] **Step 5: Update the orchestrator docstring**

In `src/dazzle/http/runtime/framework_schema.py`, replace the docstring's hand-maintained table enumeration (the `user_preferences, join_requests); process_runs ...` lines) with a pointer:

```
The complete in-scope table set is declared once in the DB-artifact registry
(dazzle.db.artifact_registry.in_baseline_tables, ADR-0047); this module creates
exactly that set. Excluded classes (event-bus {prefix} transport, ops DB,
per-tenant) are registry rows too. Do not re-list tables here.
```

- [ ] **Step 6: Run the single-source test + the snapshot unit tests**

Run: `uv run pytest tests/unit/test_in_scope_single_source.py tests/unit/ -k "framework_schema or snapshot" -q`
Expected: PASS. (The real-PG parity test `-m migration_engine` needs Postgres; it imports cleanly now and runs in CI.)

- [ ] **Step 7: Lint, commit**

```bash
uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/
uv run mypy src/dazzle/http/runtime/framework_schema_snapshot.py
git add src/dazzle/http/runtime/framework_schema_snapshot.py src/dazzle/http/runtime/framework_schema.py tests/integration/test_framework_baseline_parity_pg.py tests/unit/test_in_scope_single_source.py
git commit -m "refactor(db): IN_SCOPE_TABLES is registry-derived — collapse the triplication (#1495 follow-on)"
```

---

### Task 3: Contract — boot-entry gating biconditional + ref resolution

**Files:**
- Create: `tests/unit/test_db_artifact_contract.py`

**Interfaces:**
- Consumes: `framework_boot_entries()`, `concrete_creators()`, `DB_ARTIFACTS` (Task 1); `skip_boot_schema_ddl` name (a marker the scan looks for)
- Produces: `def _load_func_source(dotted: str) -> str` and `def _calls_skip_boot(dotted: str) -> bool` reused by later steps in this file

- [ ] **Step 1: Write the failing test (every boot_entry self-gates; refs resolve)**

```python
# tests/unit/test_db_artifact_contract.py
"""Executable contract for the DB-artifact registry (#1495 follow-on, ADR-0047).

Static (no DB). Asserts the registry's declared properties against the code:
  (1) every registered boot_entry self-gates with skip_boot_schema_ddl();
  (2) every framework function issuing app-DB CREATE TABLE/INDEX is registered;
  (3) creator/boot_entry dotted-refs resolve;
  (4) FENCED artifacts carry FORCE RLS in the generator.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib

import pytest

from dazzle.db.artifact_registry import (
    DB_ARTIFACTS,
    ArtifactClass,
    RlsPosture,
    concrete_creators,
    framework_boot_entries,
)

pytestmark = pytest.mark.gate

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _resolve(dotted: str) -> object:
    """Resolve a dotted ref of the form module.path.Class.method or module.path.func."""
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        mod_name = ".".join(parts[:i])
        try:
            obj = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr)
        return obj
    raise ModuleNotFoundError(dotted)


def _calls_skip_boot(dotted: str) -> bool:
    """True if the named function's body references skip_boot_schema_ddl."""
    fn = _resolve(dotted)
    src = inspect.getsource(fn)
    tree = ast.parse(_dedent(src))
    return any(
        isinstance(n, ast.Name) and n.id == "skip_boot_schema_ddl"
        for n in ast.walk(tree)
    )


def _dedent(src: str) -> str:
    import textwrap
    return textwrap.dedent(src)


def test_every_boot_entry_resolves() -> None:
    for ref in concrete_creators():
        _resolve(ref)  # raises if rotted


def test_registered_boot_entries_self_gate() -> None:
    failures = []
    for a in framework_boot_entries():
        assert a.boot_entry is not None
        if a.boot_ddl_gated and not _calls_skip_boot(a.boot_entry):
            failures.append(f"{a.name}: boot_entry {a.boot_entry} does not call "
                            f"skip_boot_schema_ddl() (the #1495 class)")
    assert not failures, "\n".join(failures)
```

- [ ] **Step 2: Run to verify it passes (the gates are already in place post-#1495/#1462)**

Run: `uv run pytest tests/unit/test_db_artifact_contract.py -q`
Expected: PASS (2 passed) — auth/audit/files/inbox/outbox/process boot entries all self-gate today. If any FAIL, that's a real ungated path → STOP and gate it.

- [ ] **Step 3: Commit**

```bash
uv run ruff check tests/unit/test_db_artifact_contract.py --fix && uv run ruff format tests/unit/test_db_artifact_contract.py
git add tests/unit/test_db_artifact_contract.py
git commit -m "test(db): contract — registered boot-entries self-gate + refs resolve (#1495)"
```

---

### Task 4: Contract — completeness sweep + executable excluded-classes allowlist

**Files:**
- Modify: `tests/unit/test_db_artifact_contract.py` (add the sweep + allowlist)

**Interfaces:**
- Consumes: `concrete_creators()` (Task 1), the `_resolve` helper (Task 3)
- Produces: `_DDL_DIRS`, `_ALLOWLIST` named constants documenting the excluded DDL-issuers

- [ ] **Step 1: Write the failing test (every app-DB DDL function is registered)**

Add to `tests/unit/test_db_artifact_contract.py`:

```python
# Directories whose functions issue app-DB framework DDL. A function here that
# runs CREATE TABLE/INDEX must be registered (some artifact's creator/boot_entry)
# OR named in _ALLOWLIST below.
_DDL_DIRS = (
    "src/dazzle/http/runtime",
    "src/dazzle/http/events",
    "src/dazzle/core/process",
)

# The excluded-classes list, MADE EXECUTABLE. These DDL-issuing functions are
# intentionally NOT app-DB framework tables — keep this list curated and commented.
_ALLOWLIST = frozenset(
    {
        # separate ops_integration DB (class OPS_DB, registered but on its own DB)
        "dazzle.http.runtime.ops_database.OpsDatabase._apply_migrations",
        "dazzle.http.runtime.ops_database.OpsDatabase._init_schema",
        # event-bus transport, registered as {prefix} pattern rows
        "dazzle.http.events.postgres_bus.PostgresBus._create_tables",
        # RLS POLICY ddl (not tables) — owned by rls_schema / rls_apply
        "dazzle.http.runtime.rls_schema",   # module prefix match
        "dazzle.db.rls_apply",
        # per-app full-text-search GIN / ivfflat indexes on app-entity tables
        "dazzle.http.runtime.search_schema",
        # process-table http boot path: dead-in-prod, no live caller (ADR-0044)
        "dazzle.http.runtime.process_schema.ensure_process_tables",
        # the shared ensure_* DDL helpers are reached via their registered
        # boot_entry / orchestrator; they're accounted for by creator refs.
    }
)


def _ddl_functions() -> list[tuple[str, str]]:
    """(dotted_ref, file) for every function in _DDL_DIRS whose body contains a
    string literal with CREATE TABLE or CREATE INDEX."""
    out: list[tuple[str, str]] = []
    for d in _DDL_DIRS:
        for path in (_REPO / d).rglob("*.py"):
            src = path.read_text()
            if "CREATE TABLE" not in src and "CREATE INDEX" not in src:
                continue
            tree = ast.parse(src)
            mod = _module_name(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body_src = ast.get_source_segment(src, node) or ""
                    if "CREATE TABLE" in body_src or "CREATE INDEX" in body_src:
                        out.append((_qualname(mod, node, tree), str(path)))
    return out


def _module_name(path: pathlib.Path) -> str:
    rel = path.relative_to(_REPO / "src").with_suffix("")
    return ".".join(rel.parts)


def _qualname(mod: str, fn: ast.AST, tree: ast.AST) -> str:
    """Best-effort dotted name: module.Class.method or module.func."""
    for parent in ast.walk(tree):
        if isinstance(parent, ast.ClassDef):
            if fn in ast.walk(parent):
                return f"{mod}.{parent.name}.{fn.name}"  # type: ignore[attr-defined]
    return f"{mod}.{fn.name}"  # type: ignore[attr-defined]


def _allowlisted(ref: str) -> bool:
    return any(ref == a or ref.startswith(a + ".") or ref.startswith(a) for a in _ALLOWLIST)


def test_every_app_db_ddl_function_is_registered() -> None:
    registered = concrete_creators()
    unaccounted = []
    for ref, path in _ddl_functions():
        if ref in registered or _allowlisted(ref):
            continue
        unaccounted.append(f"{ref}  ({path}) issues CREATE TABLE/INDEX but is not "
                           f"in the registry and not allowlisted — register it (and "
                           f"decide its boot_ddl_gated) or add to _ALLOWLIST with a reason")
    assert not unaccounted, "\n".join(unaccounted)
```

- [ ] **Step 2: Run — expect it to surface the real set; tune the allowlist**

Run: `uv run pytest tests/unit/test_db_artifact_contract.py::test_every_app_db_ddl_function_is_registered -q`
Expected on first run: likely FAIL listing several DDL functions (e.g. the shared `ensure_*` helpers, `version_manager`, atomic-audit helper). For each listed function, decide: is it a *registered* creator (then ensure the registry's `creator` string matches its real dotted name exactly), or an excluded DDL-issuer (then add to `_ALLOWLIST` with a one-line reason)? Iterate until the only remaining items are genuinely registered or genuinely excluded. **If a function is a real ungated app-DB boot path that ISN'T registered — that's a found #1495-sibling bug: register it with `boot_entry` set and gate it.**

- [ ] **Step 3: Run to verify it passes**

Run: `uv run pytest tests/unit/test_db_artifact_contract.py -q`
Expected: PASS (all contract tests green)

- [ ] **Step 4: Commit**

```bash
uv run ruff check tests/unit/test_db_artifact_contract.py --fix && uv run ruff format tests/unit/test_db_artifact_contract.py
git add tests/unit/test_db_artifact_contract.py src/dazzle/db/artifact_registry.py
git commit -m "test(db): contract — completeness sweep makes ungated boot-DDL un-shippable (#1495)"
```

---

### Task 5: Contract — RLS posture matches the generator

**Files:**
- Modify: `tests/unit/test_db_artifact_contract.py` (add the RLS check)

**Interfaces:**
- Consumes: `DB_ARTIFACTS`, `RlsPosture` (Task 1); `dazzle.http.runtime.rls_schema.build_all_rls_ddl` (or the fenced-set helper found in Task 1 Step 4)

- [ ] **Step 1: Write the failing test (FENCED ⇒ FORCE; NON_FENCED ⇒ not)**

Add to `tests/unit/test_db_artifact_contract.py`. Use the exact generator entry point you confirmed in Task 1 Step 4 (adjust the import/call if `build_all_rls_ddl` needs an appspec — in that case build the minimal fixture or call the lower-level fenced-table computation):

```python
def _fenced_tables_from_generator() -> frozenset[str]:
    """The set of tables the RLS generator emits FORCE ROW LEVEL SECURITY for.
    Replace the body with the confirmed call from Task 1 Step 4."""
    from dazzle.http.runtime import rls_schema
    ddl = rls_schema.build_all_rls_ddl_for_framework()  # confirmed entry point
    fenced: set[str] = set()
    for stmt in ddl:
        if "FORCE ROW LEVEL SECURITY" in stmt:
            # extract the table name token after ALTER TABLE
            fenced.add(_table_of_alter(stmt))
    return frozenset(fenced)


def test_fenced_posture_matches_generator() -> None:
    gen_fenced = _fenced_tables_from_generator()
    mismatches = []
    for a in DB_ARTIFACTS:
        if a.cls is not ArtifactClass.FRAMEWORK_INTERNAL or a.is_pattern:
            continue
        declared_fenced = a.rls is RlsPosture.FENCED
        actually_fenced = a.name in gen_fenced
        if declared_fenced != actually_fenced:
            mismatches.append(f"{a.name}: registry rls={a.rls.value} but generator "
                              f"{'emits' if actually_fenced else 'does not emit'} FORCE")
    assert not mismatches, "\n".join(mismatches)
```

> If the framework tables are NOT covered by the RLS generator at all (i.e. it only fences app-entity tables), then every FRAMEWORK_INTERNAL row is correctly `NON_FENCED` and `gen_fenced` is empty — the test still passes and documents that fact. Keep the test; it pins the invariant either way.

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/unit/test_db_artifact_contract.py::test_fenced_posture_matches_generator -q`
Expected: PASS. If it fails, correct the `rls=` field on the named registry rows to match the generator (the generator is the truth).

- [ ] **Step 3: Commit**

```bash
uv run ruff check tests/unit/test_db_artifact_contract.py --fix && uv run ruff format tests/unit/test_db_artifact_contract.py
git add tests/unit/test_db_artifact_contract.py src/dazzle/db/artifact_registry.py
git commit -m "test(db): contract — RLS posture matches rls_schema generator (#1495)"
```

---

### Task 6: `dazzle inspect db-artifacts` command

**Files:**
- Modify: `src/dazzle/cli/inspect.py` (add the `db-artifacts` command)
- Test: `tests/unit/test_inspect_db_artifacts.py`

**Interfaces:**
- Consumes: `DB_ARTIFACTS`, `ArtifactClass` (Task 1); the existing `inspect_app` Typer group (`src/dazzle/cli/inspect.py:57`)

- [ ] **Step 1: Write the failing test (text + json + class filter)**

```python
# tests/unit/test_inspect_db_artifacts.py
from __future__ import annotations

import json

from typer.testing import CliRunner

from dazzle.cli.inspect import inspect_app

runner = CliRunner()


def test_db_artifacts_text() -> None:
    res = runner.invoke(inspect_app, ["db-artifacts"])
    assert res.exit_code == 0
    assert "_dazzle_event_inbox" in res.stdout
    assert "{prefix}events" in res.stdout
    assert "framework_internal" in res.stdout


def test_db_artifacts_json() -> None:
    res = runner.invoke(inspect_app, ["db-artifacts", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    names = {a["name"] for a in payload["artifacts"]}
    assert "_dazzle_event_inbox" in names
    inbox = next(a for a in payload["artifacts"] if a["name"] == "_dazzle_event_inbox")
    assert inbox["boot_ddl_gated"] is True
    assert inbox["in_baseline"] is True


def test_db_artifacts_class_filter() -> None:
    res = runner.invoke(inspect_app, ["db-artifacts", "--class", "event_bus_transport", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    classes = {a["cls"] for a in payload["artifacts"]}
    assert classes == {"event_bus_transport"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_inspect_db_artifacts.py -q`
Expected: FAIL — `db-artifacts` is not a command (`exit_code != 0`).

- [ ] **Step 3: Add the command**

In `src/dazzle/cli/inspect.py`, add (mirroring the existing `@inspect_app.command(...)` pattern at line ~189):

```python
@inspect_app.command("db-artifacts")
def db_artifacts_command(
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of human text"),
    cls_filter: str | None = typer.Option(None, "--class", help="Filter by class (e.g. framework_internal, event_bus_transport, ops_db)"),
) -> None:
    """List every database artifact the framework manages, with its class, creator,
    boot-entry, owner, RLS posture, baseline membership, and boot-DDL gating.

    The DB-artifact registry (dazzle.db.artifact_registry, ADR-0047) is the source
    of truth; the contract test enforces the gating / in-baseline / RLS invariants.
    """
    import json as _json

    from dazzle.db.artifact_registry import DB_ARTIFACTS

    rows = [a for a in DB_ARTIFACTS if cls_filter is None or a.cls.value == cls_filter]

    if output_json:
        typer.echo(_json.dumps(
            {"artifacts": [
                {
                    "name": a.name, "cls": a.cls.value, "creator": a.creator,
                    "boot_entry": a.boot_entry, "owner": a.owner.value, "rls": a.rls.value,
                    "in_baseline": a.in_baseline, "boot_ddl_gated": a.boot_ddl_gated,
                    "is_pattern": a.is_pattern, "notes": a.notes,
                }
                for a in rows
            ]},
            indent=2,
        ))
        return

    typer.echo(f"{'artifact':<28} {'class':<20} {'base':<5} {'gated':<6} {'rls':<12}")
    typer.echo("-" * 75)
    for a in rows:
        typer.echo(f"{a.name:<28} {a.cls.value:<20} "
                   f"{'yes' if a.in_baseline else '—':<5} "
                   f"{'yes' if a.boot_ddl_gated else '—':<6} {a.rls.value:<12}")
    typer.echo(f"\n{len(rows)} artifacts. Source: dazzle.db.artifact_registry (ADR-0047). "
               f"Rules: docs/reference/db-artifacts.md")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_inspect_db_artifacts.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint, type, commit**

```bash
uv run ruff check src/dazzle/cli/inspect.py tests/unit/test_inspect_db_artifacts.py --fix && uv run ruff format src/dazzle/cli/inspect.py tests/unit/test_inspect_db_artifacts.py
uv run mypy src/dazzle/cli/inspect.py
git add src/dazzle/cli/inspect.py tests/unit/test_inspect_db_artifacts.py
git commit -m "feat(cli): dazzle inspect db-artifacts — per-artifact lens over the registry (#1495)"
```

---

### Task 7: Reference doc + MCP/index wiring

**Files:**
- Create: `docs/reference/db-artifacts.md`
- Modify: `docs/reference/index.md` (add a row)
- Modify: `src/dazzle/mcp/semantics_kb/doc_pages.toml` (add a `[pages.db_artifacts]` entry)

**Interfaces:** none (docs). Must satisfy `tests/unit/test_docs_drift.py`.

- [ ] **Step 1: Write the reference doc**

Create `docs/reference/db-artifacts.md` covering: the five dimensions; the five classes + the rule governing each (in-baseline framework tables: orchestrator-created, owner-owned, boot paths self-gate; event-bus transport: dynamic prefix, excluded, self-creating; ops-DB: separate DB; app-entity: per-DSL via the migration engine, tenant-scoped ones RLS-fenced; tenant-registry: separate lifecycle); the gating rule (independent boot paths must call `skip_boot_schema_ddl()`; orchestrator-only tables are safe via the server-level gate); and "run `dazzle inspect db-artifacts` for the live per-table facts; the registry `dazzle.db.artifact_registry` is the source, `tests/unit/test_db_artifact_contract.py` is the gate." Cross-link ADR-0044, ADR-0047, #1462, #1495.

- [ ] **Step 2: Add the index row**

In `docs/reference/index.md`, under the appropriate section table, add:

```markdown
| [DB Artifacts](db-artifacts.md) | Every database artifact the framework manages — class, owner, RLS posture, baseline membership, boot-DDL gating — and the registry + contract that keep them honest. |
```

- [ ] **Step 3: Add the doc-pages TOML entry**

In `src/dazzle/mcp/semantics_kb/doc_pages.toml`, add (pick the next free `order`):

```toml
[pages.db_artifacts]
title = "DB Artifacts"
slug = "db-artifacts"
order = <next>
intro = """
Every database artifact the framework manages, in one registry: framework-internal \
baseline tables, event-bus transport, the ops database, app-entity tables, and the \
tenant registry. Each declares its class, creator, boot-entry, owner, RLS posture, \
baseline membership, and boot-DDL gating. The registry is the source of truth; an \
executable contract enforces the gating / in-baseline / RLS invariants (catching the \
#1495 class). Run `dazzle inspect db-artifacts` for the live per-table view.
"""
```

- [ ] **Step 4: Run the docs drift gate**

Run: `uv run pytest tests/unit/test_docs_drift.py -q`
Expected: PASS. If it complains the index/doc_pages are out of sync, reconcile per its message (it may require the slug to appear in both `index.md` and `doc_pages.toml`).

- [ ] **Step 5: Commit**

```bash
git add docs/reference/db-artifacts.md docs/reference/index.md src/dazzle/mcp/semantics_kb/doc_pages.toml
git commit -m "docs(reference): db-artifacts page — the agent-readable DB source of truth (#1495)"
```

---

### Task 8: ADR-0047 + ADR-0044 amendment + INDEX + CLAUDE.md pointer

**Files:**
- Create: `docs/adr/0047-db-artifact-registry.md`
- Modify: `docs/adr/0044-complete-ci-managed-framework-migration-baseline.md` (forward-ref header only)
- Modify: `docs/adr/INDEX.md` (add ADR-0047)
- Modify: `.claude/CLAUDE.md` (add a DB pointer bullet under "Architectural Decisions")

**Interfaces:** none.

- [ ] **Step 1: Write ADR-0047**

Create `docs/adr/0047-db-artifact-registry.md` — match the house ADR format (header with `**Status:** Accepted` + `**Builds on:**` cross-links to ADR-0008/0017/0044/0045/0036/0037). Decision: "the DB-artifact registry (`dazzle.db.artifact_registry`) is the single source of truth for artifact metadata; `IN_SCOPE_TABLES` is registry-derived; the executable contract (`tests/unit/test_db_artifact_contract.py`) enforces the boot-entry gating invariant + a completeness sweep + RLS posture." Context: the #1495 diagnosis required reconstructing five scattered facts; the in-scope list was triplicated. Consequences: new framework tables and new boot-DDL paths must register; the contract makes the #1495 class un-shippable.

- [ ] **Step 2: Amend ADR-0044 (forward-ref header, body unchanged)**

At the top of `docs/adr/0044-...md`, under the existing `**Status:** Accepted` line, add:

```markdown
**Amended by:** ADR-0047 — artifact *membership and per-artifact metadata* (class /
owner / RLS posture / boot-DDL gating) is now sourced from the DB-artifact registry
(`dazzle.db.artifact_registry`); this ADR's `IN_SCOPE_TABLES` is registry-derived.
ADR-0044 remains the record of the baseline *construction + parity mechanism* (the
squash, the shared-DDL-core, the three-way real-PG parity gate).
```

- [ ] **Step 3: Add ADR-0047 to the index**

In `docs/adr/INDEX.md`, add the ADR-0047 row in the same format as the surrounding entries.

- [ ] **Step 4: Add the CLAUDE.md pointer**

In `.claude/CLAUDE.md`, under `## Architectural Decisions`, after the `**All schema changes via Alembic**` bullet, add:

```markdown
- **DB artifacts have one registry** — before adding a table, boot-DDL, or RLS to the framework, read `docs/reference/db-artifacts.md` or run `dazzle inspect db-artifacts`. `dazzle.db.artifact_registry` is the source of truth (class/owner/RLS/baseline/gating); `tests/unit/test_db_artifact_contract.py` enforces the boot-entry gating invariant + completeness sweep — a new ungated boot-DDL path (the #1495 class) fails CI until registered+gated (ADR-0047, supersedes the hand-synced `IN_SCOPE_TABLES`).
```

- [ ] **Step 5: Run the ADR/docs drift gates**

Run: `uv run pytest tests/unit/ -k "adr or docs_drift or claude" -q`
Expected: PASS. (If an ADR-index drift test exists and flags the new ADR, reconcile per its message.)

- [ ] **Step 6: Commit**

```bash
git add docs/adr/0047-db-artifact-registry.md docs/adr/0044-complete-ci-managed-framework-migration-baseline.md docs/adr/INDEX.md .claude/CLAUDE.md
git commit -m "docs(adr): ADR-0047 DB-artifact registry + ADR-0044 scope amendment (#1495)"
```

---

### Task 9: Final regression, CHANGELOG, bump, ship

**Files:**
- Modify: `CHANGELOG.md`, version files (via `/bump patch`)

- [ ] **Step 1: Full regression gate**

```bash
uv run pytest tests/ -m "not e2e" -q
uv run mypy src/dazzle
uv run lint-imports
```
Expected: PASS / `Contracts: 6 kept, 0 broken` (the registry in `db/` imports only `core`/stdlib, so layer contracts hold). Note any pre-existing unrelated failures and continue.

- [ ] **Step 2: CHANGELOG entry**

Add under `## [Unreleased]` → `### Added`:

```markdown
- **DB-artifact registry — single source of truth for every framework database artifact (#1495 follow-on, ADR-0047).** `dazzle.db.artifact_registry` declares each artifact's class / creator / boot-entry / owner / RLS posture / baseline membership / boot-DDL gating; `framework_schema_snapshot.IN_SCOPE_TABLES` and the real-PG parity test are now registry-derived (collapsing the triplicated list). New `dazzle inspect db-artifacts` lens + `docs/reference/db-artifacts.md`. The executable contract (`tests/unit/test_db_artifact_contract.py`) asserts every registered boot-entry self-gates with `skip_boot_schema_ddl()` and that every framework function issuing app-DB `CREATE TABLE/INDEX` is registered — making the #1495 class (ungated boot-DDL under a non-owner role) un-shippable. ADR-0044 amended (scope narrowed to the baseline-construction mechanism).
```

- [ ] **Step 3: Bump + commit + push**

```bash
/bump patch        # or run the sed block from the bump skill
uv lock
git add -A
git commit -m "release: vX.Y.Z — DB-artifact registry + executable contract (#1495 follow-on)"
git push
```

- [ ] **Step 4: Monitor CI**

```bash
gh run list --branch main --limit 3
```
Expected: green. If `lint`/`coverage`/drift fails, fix and re-push (the artefact-coverage gate, api-surface drift, and docs drift are the likely sensitive ones).

---

## Self-Review

**Spec coverage:**
- Registry-as-source + declared properties → Task 1. ✓
- Collapse triplication → Task 2. ✓
- Executable contract: boot-entry gating → Task 3; completeness sweep + allowlist → Task 4; RLS posture → Task 5. ✓ (creator/boot_entry resolve → Task 3.)
- `dazzle inspect db-artifacts` → Task 6. ✓
- Reference doc + index + doc_pages → Task 7. ✓
- ADR-0047 + ADR-0044 amendment + CLAUDE.md pointer → Task 8. ✓
- Per-table-vs-class-row scope split → Task 1 data (FRAMEWORK_INTERNAL/EVENT_BUS_TRANSPORT/OPS_DB enumerated; APP_ENTITY/TENANT_REGISTRY as `is_pattern` class rows). ✓
- Out-of-scope respected: no orchestrator DDL rewrite; RLS check static; no migration-engine change. ✓

**Placeholder scan:** The two provisional fields (orchestrator-only classification + RLS posture) are not left vague — Task 1 Step 4 is an explicit *verification* with commands that confirm/correct them; Task 5 pins RLS to the generator. The completeness-sweep allowlist (Task 4 Step 2) is tuned against real test output, not guessed.

**Type consistency:** `Artifact` fields (`name/cls/creator/boot_entry/owner/rls/in_baseline/boot_ddl_gated/notes/is_pattern`) are used identically in Tasks 1/3/4/5/6. Helpers `in_baseline_tables` / `framework_boot_entries` / `concrete_creators` are defined in Task 1 and consumed by Tasks 2/3/4 with matching signatures. Enum value strings (`framework_internal`, `event_bus_transport`, `ops_db`) used in the CLI filter (Task 6) match the `StrEnum` definitions (Task 1).

**Risk note carried into execution:** Task 1 Step 4 and Task 4 Step 2 may *discover* a latent ungated boot path among the stores currently classified orchestrator-only (token/device/grant/otp/recovery). That is a feature — if found, it's a real #1495-sibling: register it with `boot_entry` + gate it as a small in-task fix, and note it in the commit.
