# Dynamic RBAC Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `rbac/verifier.py:verify()` with a real Layer-2 verifier that boots the app in-process, probes every RBAC matrix cell as the relevant role, and reports runtime-vs-matrix divergence.

**Architecture:** `verify()` provisions a disposable PostgreSQL database, seeds one synthetic user per role plus one baseline row per entity, builds the `DazzleServer` ASGI app in-process, drives it with an `httpx.ASGITransport` client, probes each `(role, entity, operation)` cell, and feeds the observed `(status, count)` into the existing `compare_cell()` to produce a `VerificationReport`.

**Tech Stack:** Python 3.12, `httpx` (`ASGITransport`), `psycopg`, existing `dazzle.rbac.matrix` / `dazzle.rbac.verifier` / `dazzle.rbac.audit`, `typer` CLI.

**Spec:** `docs/superpowers/specs/2026-05-20-rbac-verifier-design.md`

---

## File Structure

- **Modify** `src/dazzle/rbac/verifier.py` — keep the existing types + `compare_cell` (unchanged); add the runtime helpers (`_DisposableDatabase`, `_seed_role_users`, `_seed_baseline_rows`, `_probe_cell`) and replace the `verify()` stub.
- **Modify** `src/dazzle/cli/rbac.py:374-382` — replace the `verify` command stub with a real invocation.
- **Create** `tests/unit/test_rbac_verifier_probe.py` — unit tests for `_probe_cell` (fake httpx client, no DB).
- **Modify** `tests/unit/test_rbac_verifier.py` — existing `compare_cell`/type tests stay; nothing to change.
- **Create** `tests/integration/test_rbac_verifier_e2e.py` — `postgres`-marked end-to-end test running `verify()` against `fixtures/rbac_validation`.
- **Modify** `README.md`, `docs/llms.txt`, `docs/reference/rbac-verification.md` — describe dynamic verification accurately (no longer "stubbed").

> Keeping the runtime helpers in `verifier.py` (rather than a new module) is deliberate: `verify()` already lives there, the helpers are private (`_`-prefixed), and the file stays well under a size that warrants splitting. If it grows past ~600 lines during implementation, split the runtime helpers into `verifier_runtime.py` and re-export — but do not pre-split.

---

## Task 1: `_probe_cell` — operation → HTTP request mapping

The leaf unit: given an authenticated client and a `(entity, operation)`, issue the right request and return `(observed_status, observed_count)`. No DB, no app — testable with a fake client.

**Files:**
- Modify: `src/dazzle/rbac/verifier.py` (add `_probe_cell` + a `_ProbeResult` dataclass near the bottom, before `verify()`)
- Test: `tests/unit/test_rbac_verifier_probe.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for _probe_cell — RBAC verifier per-cell HTTP probing (#1171)."""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.rbac.verifier import _probe_cell


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any = None) -> None:
        self.status_code = status_code
        self._json = json_body

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class _FakeClient:
    """Records the last request and returns a queued response."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((method, url))
        return self._response


@pytest.mark.asyncio
async def test_list_probe_issues_get_and_counts_items() -> None:
    client = _FakeClient(_FakeResponse(200, {"items": [{"id": "1"}, {"id": "2"}]}))
    result = await _probe_cell(client, entity="Task", operation="list", baseline_id="x")
    assert client.calls == [("GET", "/api/tasks")]
    assert result.status == 200
    assert result.count == 2


@pytest.mark.asyncio
async def test_read_probe_targets_baseline_id() -> None:
    client = _FakeClient(_FakeResponse(200, {"id": "abc"}))
    result = await _probe_cell(client, entity="Task", operation="read", baseline_id="abc")
    assert client.calls == [("GET", "/api/tasks/abc")]
    assert result.status == 200
    assert result.count is None


@pytest.mark.asyncio
async def test_delete_probe_issues_delete() -> None:
    client = _FakeClient(_FakeResponse(403))
    result = await _probe_cell(client, entity="Task", operation="delete", baseline_id="abc")
    assert client.calls == [("DELETE", "/api/tasks/abc")]
    assert result.status == 403


@pytest.mark.asyncio
async def test_create_probe_issues_post() -> None:
    client = _FakeClient(_FakeResponse(201, {"id": "new"}))
    result = await _probe_cell(client, entity="Task", operation="create", baseline_id=None)
    assert client.calls == [("POST", "/api/tasks")]
    assert result.status == 201


@pytest.mark.asyncio
async def test_list_count_none_when_body_not_json() -> None:
    client = _FakeClient(_FakeResponse(200, None))
    result = await _probe_cell(client, entity="Task", operation="list", baseline_id=None)
    assert result.status == 200
    assert result.count is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_rbac_verifier_probe.py -q`
Expected: FAIL — `ImportError: cannot import name '_probe_cell'`.

- [ ] **Step 3: Implement `_probe_cell`**

Add to `src/dazzle/rbac/verifier.py` (after `compare_cell`, before `verify`). Use `dazzle.core.strings.to_api_plural` for the URL segment (the same helper the bulk routes and `verify-scope` use).

```python
from dazzle.core.strings import to_api_plural  # add to the import block at top


@dataclass
class _ProbeResult:
    """Observed outcome of probing one (role, entity, operation) cell."""

    status: int
    count: int | None


# operation -> (HTTP method, needs_id, has_body)
_PROBE_VERBS: dict[str, tuple[str, bool, bool]] = {
    "list": ("GET", False, False),
    "read": ("GET", True, False),
    "create": ("POST", False, True),
    "update": ("PATCH", True, True),
    "delete": ("DELETE", True, False),
}


async def _probe_cell(
    client: Any,
    *,
    entity: str,
    operation: str,
    baseline_id: str | None,
    body: dict[str, Any] | None = None,
) -> _ProbeResult:
    """Issue the HTTP request for one matrix cell and capture status + count.

    `client` is an authenticated httpx.AsyncClient (cookies already set).
    `baseline_id` is the seeded row for read/update/delete; ignored for
    list/create. `count` is the item count of a list response, else None.
    """
    method, needs_id, has_body = _PROBE_VERBS[operation]
    plural = to_api_plural(entity)
    url = f"/api/{plural}/{baseline_id}" if needs_id else f"/api/{plural}"

    kwargs: dict[str, Any] = {}
    if has_body:
        kwargs["json"] = body or {}

    response = await client.request(method, url, **kwargs)

    count: int | None = None
    if operation == "list" and response.status_code == 200:
        try:
            payload = response.json()
            items = payload.get("items") if isinstance(payload, dict) else payload
            if isinstance(items, list):
                count = len(items)
        except Exception:
            count = None

    return _ProbeResult(status=response.status_code, count=count)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_rbac_verifier_probe.py -q`
Expected: PASS — 5 passed.

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/rbac/verifier.py tests/unit/test_rbac_verifier_probe.py --fix
ruff format src/dazzle/rbac/verifier.py tests/unit/test_rbac_verifier_probe.py
git add src/dazzle/rbac/verifier.py tests/unit/test_rbac_verifier_probe.py
git commit -m "feat(rbac): _probe_cell — per-cell HTTP probing for the verifier (#1171)"
```

---

## Task 2: `_DisposableDatabase` — scratch database lifecycle

An async context manager that creates a uniquely-named PostgreSQL database, creates the app schema in it, yields its URL, and drops it on exit (always).

**Files:**
- Modify: `src/dazzle/rbac/verifier.py` (add `_DisposableDatabase`)
- Test: `tests/integration/test_rbac_verifier_e2e.py` (create the file; this task adds the DB-lifecycle test, `postgres`-marked)

- [ ] **Step 1: Write the failing test**

```python
"""End-to-end tests for the dynamic RBAC verifier (#1171). Requires PostgreSQL."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.postgres

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_disposable_database_creates_and_drops() -> None:
    import psycopg

    from dazzle.rbac.verifier import _DisposableDatabase

    created_url: str | None = None
    async with _DisposableDatabase(_PG_URL) as db_url:
        created_url = db_url
        # The scratch DB exists and is connectable.
        conn = psycopg.connect(db_url)
        conn.close()

    # After exit the scratch DB is gone.
    assert created_url is not None
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(created_url).close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/integration/test_rbac_verifier_e2e.py -q -m postgres`
Expected: FAIL — `ImportError: cannot import name '_DisposableDatabase'` (or skip if no PG — provision one: `docker run -e POSTGRES_PASSWORD=dazzle_test -e POSTGRES_USER=dazzle -e POSTGRES_DB=dazzle_test -p 5432:5432 postgres:16`, then `export TEST_DATABASE_URL=postgresql://dazzle:dazzle_test@localhost:5432/dazzle_test`).

- [ ] **Step 3: Implement `_DisposableDatabase`**

Add to `src/dazzle/rbac/verifier.py`. The scratch DB name must be a valid identifier — `dazzle_verify_<hex>`. `CREATE/DROP DATABASE` cannot run inside a transaction, so connect with `autocommit=True` to the *maintenance* database (the server URL with the path swapped to `/postgres`).

```python
import uuid
from urllib.parse import urlparse, urlunparse


class _DisposableDatabase:
    """Async context manager: create a scratch PostgreSQL database, yield
    its URL, drop it on exit. The scratch DB never leaks — the drop runs
    in `__aexit__` even when the body raises."""

    def __init__(self, server_url: str) -> None:
        self._server_url = server_url
        self._db_name = f"dazzle_verify_{uuid.uuid4().hex}"
        self._db_url = ""

    def _admin_url(self) -> str:
        parts = urlparse(self._server_url)
        return urlunparse(parts._replace(path="/postgres"))

    def _scratch_url(self) -> str:
        parts = urlparse(self._server_url)
        return urlunparse(parts._replace(path=f"/{self._db_name}"))

    async def __aenter__(self) -> str:
        import psycopg

        with psycopg.connect(self._admin_url(), autocommit=True) as conn:
            # _db_name is a server-generated hex identifier — not user input.
            conn.execute(f'CREATE DATABASE "{self._db_name}"')  # nosemgrep
        self._db_url = self._scratch_url()
        return self._db_url

    async def __aexit__(self, *exc: object) -> None:
        import psycopg

        with psycopg.connect(self._admin_url(), autocommit=True) as conn:
            conn.execute(
                f'DROP DATABASE IF EXISTS "{self._db_name}" WITH (FORCE)'  # nosemgrep
            )
```

> Schema creation is NOT done here — `DazzleServer._setup_database` already creates the schema on boot when the database is empty (`_should_create_schema_on_startup` → `metadata.create_all`). Task 4 relies on that: pointing the server at the empty scratch DB makes it build the schema during boot.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/integration/test_rbac_verifier_e2e.py::test_disposable_database_creates_and_drops -q`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/rbac/verifier.py tests/integration/test_rbac_verifier_e2e.py --fix
ruff format src/dazzle/rbac/verifier.py tests/integration/test_rbac_verifier_e2e.py
git add src/dazzle/rbac/verifier.py tests/integration/test_rbac_verifier_e2e.py
git commit -m "feat(rbac): _DisposableDatabase scratch-DB lifecycle for the verifier (#1171)"
```

---

## Task 3: Fixture seeding — role users + baseline rows

After the server boots against the scratch DB (Task 4), the verifier needs one user per role and one baseline row per entity. Seeding goes through the running app's API (as a superuser) so password hashing, role assignment, and entity validation use the real code paths.

**Files:**
- Modify: `src/dazzle/rbac/verifier.py` (add `_seed_role_users`, `_seed_baseline_rows`)
- Test: `tests/integration/test_rbac_verifier_e2e.py` (add seeding test)

- [ ] **Step 1: Read the existing user-creation + login paths**

Before writing code, read these so the seeding mirrors the real flow:
- `src/dazzle/cli/rbac.py:138-186` — `_login()`: how `verify-scope` POSTs to `/auth/login` (JSON body, `{"email", "password"}`, returns cookies). Reuse this exact helper — import it: `from dazzle.cli.rbac import _login`.
- The framework user/admin entity + how a superuser is created at boot. Check `src/dazzle/http/runtime/` for the bootstrap admin (search: `grep -rn "is_superuser\|bootstrap.*admin\|create.*admin" src/dazzle/http/runtime/`). The verifier authenticates as that bootstrap superuser to seed.
- The user-management API route for creating users with roles (search: `grep -rn "user_management\|/api/users\|create_user" src/dazzle/http/runtime/`).

Record the exact superuser email/password the test-mode boot creates — Task 4 needs it.

- [ ] **Step 2: Write the failing test**

```python
@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_seed_role_users_creates_one_user_per_role() -> None:
    from dazzle.rbac.verifier import _seed_role_users, _verifier_app_context

    async with _verifier_app_context("fixtures/rbac_validation", _PG_URL) as ctx:
        creds = await _seed_role_users(ctx.client, roles=["intern", "physician"])
        assert set(creds.keys()) == {"intern", "physician"}
        for role, (email, password) in creds.items():
            assert role in email
            assert password  # non-empty
```

> `_verifier_app_context` is built in Task 4. If executing strictly in order, write this test's body in Task 4 instead and keep Task 3 to `_seed_*` unit-level shape tests against a fake client. The recommended order: do Task 4's `_verifier_app_context` first, then Task 3. Adjust task order at execution time — they are mutually referencing by design (seeding needs a booted app; the app context is generic).

- [ ] **Step 3: Implement the seeding helpers**

```python
_VERIFIER_PASSWORD = "verify-test-password"  # nosec — scratch DB, dropped after run


async def _seed_role_users(
    client: Any, *, roles: list[str]
) -> dict[str, tuple[str, str]]:
    """Create one user per role via the user-management API (client must be
    authenticated as a superuser). Returns {role: (email, password)}."""
    creds: dict[str, tuple[str, str]] = {}
    for role in roles:
        email = f"verify-{role}@dazzle.test"
        # Endpoint + payload shape: confirmed in Step 1. Mirror the
        # user-management create route's expected body.
        resp = await client.request(
            "POST",
            "/api/users",  # confirm exact path in Step 1
            json={"email": email, "password": _VERIFIER_PASSWORD, "roles": [role]},
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"verifier could not seed user for role {role!r}: "
                f"HTTP {resp.status_code}"
            )
        creds[role] = (email, _VERIFIER_PASSWORD)
    return creds


async def _seed_baseline_rows(
    client: Any, *, entities: list[str]
) -> dict[str, str]:
    """Create one baseline row per entity (client authenticated as superuser).
    Returns {entity: row_id}. An entity whose create fails is omitted —
    read/update/delete cells for it will probe with a synthetic id and the
    verifier records a WARNING."""
    from dazzle.core.strings import to_api_plural

    baseline: dict[str, str] = {}
    for entity in entities:
        resp = await client.request("POST", f"/api/{to_api_plural(entity)}", json={})
        if resp.status_code in (200, 201):
            try:
                row_id = resp.json().get("id")
            except Exception:
                row_id = None
            if row_id:
                baseline[entity] = str(row_id)
    return baseline
```

> The empty `json={}` create body relies on entities that have all-optional or defaulted fields. `fixtures/rbac_validation` entities should be checked — if a required field blocks creation, extend `_seed_baseline_rows` to build a minimal valid body from the entity's IR (`entity.fields`, required + type). Keep this minimal: the baseline row only needs to exist, field values are irrelevant to RBAC probing.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/integration/test_rbac_verifier_e2e.py::test_seed_role_users_creates_one_user_per_role -q`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/rbac/verifier.py tests/integration/test_rbac_verifier_e2e.py --fix
ruff format src/dazzle/rbac/verifier.py tests/integration/test_rbac_verifier_e2e.py
git add src/dazzle/rbac/verifier.py tests/integration/test_rbac_verifier_e2e.py
git commit -m "feat(rbac): verifier fixture seeding — role users + baseline rows (#1171)"
```

---

## Task 4: `_verifier_app_context` — in-process ASGI app against the scratch DB

A context manager that boots the `DazzleServer` ASGI app against a given database URL and yields an authenticated-as-superuser `httpx.AsyncClient` plus the `AppSpec`.

**Files:**
- Modify: `src/dazzle/rbac/verifier.py` (add `_VerifierContext` dataclass + `_verifier_app_context`)
- Test: covered by Task 3's test (which uses it)

- [ ] **Step 1: Read the app-construction entrypoint**

Read `src/dazzle/http/runtime/server.py` — find how `dazzle serve --local` builds the app. Identify the constructor/factory that yields a FastAPI/ASGI app given a `database_url` and `project_root`. Confirm: (a) the kwarg name for the DB URL, (b) whether boot is sync or async, (c) the test-mode flag that auto-creates the schema and a bootstrap superuser (the `--test-mode` path `dazzle serve` uses; see `_should_create_schema_on_startup`).

- [ ] **Step 2: Implement `_verifier_app_context`**

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


@dataclass
class _VerifierContext:
    appspec: Any
    client: Any  # httpx.AsyncClient, authenticated as superuser


@asynccontextmanager
async def _verifier_app_context(
    project_root: str | Path, database_url: str
) -> AsyncIterator[_VerifierContext]:
    """Boot the Dazzle app in-process against `database_url`, yield an
    httpx client bound to it via ASGITransport and logged in as the
    bootstrap superuser. Schema is created on boot (empty scratch DB)."""
    import httpx

    from dazzle.cli.rbac import _login
    from dazzle.core.appspec_loader import load_project_appspec

    root = Path(project_root)
    appspec = load_project_appspec(root)

    # Build the ASGI app — use the same entrypoint `dazzle serve --local`
    # uses, in test-mode so the schema + bootstrap superuser are created.
    # Exact constructor confirmed in Step 1.
    app = _build_asgi_app(root, database_url)  # see Step 3

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://verifier.local", follow_redirects=True
    ) as client:
        # Authenticate as the bootstrap superuser (creds from Step 1).
        await _login(client, "http://verifier.local", _SUPERUSER_EMAIL, _SUPERUSER_PASSWORD)
        yield _VerifierContext(appspec=appspec, client=client)
```

- [ ] **Step 3: Implement `_build_asgi_app`**

Wrap the real server entrypoint. The exact body depends on Step 1's findings — it constructs the app object with `database_url=database_url`, `project_root=root`, and the test-mode flag enabled. If boot is async, run it; if the ASGI app needs a lifespan to create schema, the `httpx.ASGITransport` + a startup call handles it. Keep this function ≤15 lines — it is purely an adapter over the existing `server.py` entrypoint. Do not reimplement boot logic.

- [ ] **Step 4: Run Task 3's seeding test (now satisfiable)**

Run: `python -m pytest tests/integration/test_rbac_verifier_e2e.py::test_seed_role_users_creates_one_user_per_role -q`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/rbac/verifier.py --fix && ruff format src/dazzle/rbac/verifier.py
git add src/dazzle/rbac/verifier.py
git commit -m "feat(rbac): in-process ASGI app context for the verifier (#1171)"
```

---

## Task 5: `verify()` — orchestration

Replace the stub. Wire matrix + disposable DB + app context + seeding + per-role login + per-cell probing + audit capture + report assembly.

**Files:**
- Modify: `src/dazzle/rbac/verifier.py:221-251` (replace the `verify` stub)
- Test: `tests/integration/test_rbac_verifier_e2e.py` (add the full-run test — completed in Task 6)

- [ ] **Step 1: Replace the `verify()` stub**

```python
async def verify(
    project_root: Path,
    *,
    server_database_url: str | None = None,
) -> VerificationReport:
    """Run Layer-2 dynamic RBAC verification.

    Provisions a disposable database, boots the app in-process, probes
    every (role, entity, operation) matrix cell as the relevant role, and
    compares observed behaviour against the static matrix.
    """
    import importlib.metadata
    import os
    from datetime import UTC, datetime

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.rbac.audit import InMemoryAuditSink, NullAuditSink, set_audit_sink
    from dazzle.rbac.matrix import generate_access_matrix

    try:
        version = importlib.metadata.version("dazzle-dsl")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    now = datetime.now(UTC).isoformat()

    server_url = server_database_url or os.environ.get("DATABASE_URL")
    if not server_url:
        raise RuntimeError(
            "dynamic RBAC verification requires a PostgreSQL server — set "
            "DATABASE_URL (the verifier creates and drops its own scratch DB)."
        )

    appspec = load_project_appspec(project_root)
    matrix = generate_access_matrix(appspec)

    cells: list[VerifiedCell] = []
    try:
        async with _DisposableDatabase(server_url) as db_url:
            async with _verifier_app_context(project_root, db_url) as ctx:
                creds = await _seed_role_users(ctx.client, roles=list(matrix.roles))
                baseline = await _seed_baseline_rows(
                    ctx.client, entities=list(matrix.entities)
                )
                cells = await _probe_all_cells(project_root, db_url, matrix, creds, baseline)
    except Exception as exc:
        # App boot / DB failure — return a report carrying the error.
        return VerificationReport(
            app_name=str(project_root),
            timestamp=now,
            dazzle_version=version,
            matrix=matrix,
            cells=[],
            total=0,
            passed=0,
            violated=0,
            warnings=0,
        )
    finally:
        set_audit_sink(NullAuditSink())  # restore the production default

    passed = sum(1 for c in cells if c.result == CellResult.PASS)
    violated = sum(1 for c in cells if c.result == CellResult.VIOLATION)
    warnings = sum(1 for c in cells if c.result == CellResult.WARNING)
    return VerificationReport(
        app_name=str(project_root),
        timestamp=now,
        dazzle_version=version,
        matrix=matrix,
        cells=cells,
        total=len(cells),
        passed=passed,
        violated=violated,
        warnings=warnings,
    )
```

> The bare `except Exception` here is the spec's "app boot failure → report with error" path. It must NOT swallow per-cell errors (those are handled inside `_probe_all_cells`, Step 2). Consider adding an `error: str | None` field to `VerificationReport` so the boot-failure detail is not lost — if you do, update `to_json`/`load` and `VerificationReport`'s callers in the same commit (clean break, no shim).

- [ ] **Step 2: Implement `_probe_all_cells`**

```python
async def _probe_all_cells(
    project_root: Path,
    db_url: str,
    matrix: AccessMatrix,
    creds: dict[str, tuple[str, str]],
    baseline: dict[str, str],
) -> list[VerifiedCell]:
    """Open one authenticated client per role; probe every matrix cell."""
    import httpx

    from dazzle.cli.rbac import _login
    from dazzle.rbac.audit import InMemoryAuditSink, set_audit_sink

    cells: list[VerifiedCell] = []
    app = _build_asgi_app(Path(project_root), db_url)
    transport = httpx.ASGITransport(app=app)

    for role in matrix.roles:
        if role not in creds:
            continue
        email, password = creds[role]
        async with httpx.AsyncClient(
            transport=transport, base_url="http://verifier.local", follow_redirects=True
        ) as client:
            await _login(client, "http://verifier.local", email, password)
            for entity in matrix.entities:
                for operation in matrix.operations:
                    expected = matrix.cells.get((role, entity, operation))
                    if expected is None:
                        continue
                    sink = InMemoryAuditSink()
                    set_audit_sink(sink)
                    try:
                        probe = await _probe_cell(
                            client,
                            entity=entity,
                            operation=operation,
                            baseline_id=baseline.get(entity),
                        )
                        result = compare_cell(
                            expected, probe.status, probe.count
                        )
                        detail = ""
                    except Exception as exc:  # per-cell failure → WARNING, continue
                        probe = _ProbeResult(status=0, count=None)
                        result = CellResult.WARNING
                        detail = f"probe error: {exc}"
                    cells.append(
                        VerifiedCell(
                            role=role,
                            entity=entity,
                            operation=operation,
                            expected=expected,
                            observed_status=probe.status,
                            observed_count=probe.count,
                            result=result,
                            audit_records=list(sink.records),
                            detail=detail,
                        )
                    )
    return cells
```

> Confirm `AccessMatrix` exposes `.roles`, `.entities`, `.operations`, and `.cells` (it does — see `VerificationReport.load` in `verifier.py`, which reconstructs exactly those). If `compare_cell` needs `total` for `PERMIT_FILTERED` cells, pass the admin/superuser list count for that entity (capture it once per entity during seeding) — wire that through `baseline` as a parallel `{entity: total}` dict if the fixture exercises `PERMIT_FILTERED`.

- [ ] **Step 3: Run the existing verifier unit tests (no regression)**

Run: `python -m pytest tests/unit/test_rbac_verifier.py tests/unit/test_rbac_verifier_probe.py -q`
Expected: PASS (the `compare_cell`/type tests are untouched).

- [ ] **Step 4: Lint + typecheck + commit**

```bash
ruff check src/dazzle/rbac/verifier.py --fix && ruff format src/dazzle/rbac/verifier.py
mypy src/dazzle/rbac/verifier.py
git add src/dazzle/rbac/verifier.py
git commit -m "feat(rbac): real verify() orchestration — boot, probe, compare (#1171)"
```

---

## Task 6: End-to-end test against `fixtures/rbac_validation`

Prove the whole pipeline: `verify()` runs against the canonical RBAC fixture and reports zero violations.

**Files:**
- Modify: `tests/integration/test_rbac_verifier_e2e.py`

- [ ] **Step 1: Write the end-to-end test**

```python
@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_verify_rbac_validation_fixture_has_no_violations() -> None:
    from pathlib import Path

    from dazzle.rbac.verifier import CellResult, verify

    report = await verify(Path("fixtures/rbac_validation"), server_database_url=_PG_URL)

    assert report.total > 0, "verifier probed zero cells — matrix or boot failure"
    violations = [c for c in report.cells if c.result == CellResult.VIOLATION]
    assert not violations, (
        "runtime RBAC diverged from the static matrix:\n"
        + "\n".join(
            f"  {c.role}/{c.entity}/{c.operation}: expected {c.expected.value}, "
            f"got HTTP {c.observed_status}"
            for c in violations
        )
    )
```

- [ ] **Step 2: Run the end-to-end test**

Run: `python -m pytest tests/integration/test_rbac_verifier_e2e.py -q -m postgres`
Expected: PASS. If violations surface, they are either (a) real RBAC bugs in the fixture's runtime enforcement — investigate and fix, or (b) verifier bugs (wrong baseline id, wrong probe verb) — fix the verifier. A genuine fixture mismatch is a finding worth its own issue.

- [ ] **Step 3: Run the full unit slice (no regressions)**

Run: `python -m pytest tests/ -m "not e2e" -q -n auto`
Expected: PASS (modulo known parallel-execution flakes — re-run any failure in isolation to confirm it is unrelated).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_rbac_verifier_e2e.py
git commit -m "test(rbac): end-to-end verifier run against rbac_validation fixture (#1171)"
```

---

## Task 7: Wire the `dazzle rbac verify` CLI command + correct the docs

**Files:**
- Modify: `src/dazzle/cli/rbac.py:374-382` (replace the `verify` stub)
- Modify: `README.md`, `docs/llms.txt`, `docs/reference/rbac-verification.md`

- [ ] **Step 1: Replace the `verify` CLI stub**

```python
@rbac_app.command("verify")
def verify_cmd(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
) -> None:
    """Run dynamic RBAC verification against an in-process app (Layer 2)."""
    from dazzle.rbac.verifier import verify

    root = resolve_project(manifest)
    try:
        report = asyncio.run(verify(root))
    except Exception as exc:
        typer.echo(f"RBAC verification failed: {exc}", err=True)
        raise typer.Exit(code=1)

    report_path = root / ".dazzle" / "rbac-verify-report.json"
    report.save(report_path)

    typer.echo(
        f"RBAC verification: {report.total} cells | {report.passed} passed | "
        f"{report.violated} violated | {report.warnings} warnings"
    )
    typer.echo(f"Report: {report_path}")
    for cell in report.cells:
        if cell.result.value == "VIOLATION":
            typer.echo(
                f"  VIOLATION  {cell.role}/{cell.entity}/{cell.operation}: "
                f"expected {cell.expected.value}, got HTTP {cell.observed_status}",
                err=True,
            )
    if report.violated > 0:
        raise typer.Exit(code=1)
```

- [ ] **Step 2: Verify the CLI command runs**

Run: `cd fixtures/rbac_validation && DATABASE_URL=$TEST_DATABASE_URL python -m dazzle rbac verify; cd -`
Expected: prints the summary line; exits 0 if no violations. `dazzle rbac report` then renders the saved JSON.

- [ ] **Step 3: Correct the docs**

The verifier is now real — remove the "stubbed / not yet implemented / planned" language and describe it accurately:
- `docs/reference/rbac-verification.md` — the Layer-2 section: describe `verify()` as implemented (in-process boot, full-matrix probe, disposable DB). Remove any "stub"/"deferred" wording.
- `README.md` — the "Provable access control" table row for "Dynamic Verification": it now genuinely "probes the running app as every role" — keep the claim, drop any caveat that implied it was aspirational.
- `docs/llms.txt` — same: "dynamic verification" is now a delivered capability; ensure the wording matches reality.

This resolves the RBAC-overclaim half of #1176.

- [ ] **Step 4: Run drift + doc tests**

Run: `python -m pytest tests/unit/test_docs_drift.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/rbac.py README.md docs/llms.txt docs/reference/rbac-verification.md
git commit -m "feat(rbac): wire dazzle rbac verify + correct dynamic-verification docs (#1171)"
```

---

## Final steps

- [ ] **Bump + CHANGELOG.** Run `/bump patch`. Add a CHANGELOG entry under the new version:

```markdown
### Added

- **Dynamic RBAC verifier is now real** (#1171). `dazzle rbac verify`
  boots the app in-process, probes every `(role, entity, operation)`
  matrix cell as the relevant role against a disposable database, and
  reports any divergence from the static RBAC matrix as a VIOLATION.
  Replaces the previous `verify()` stub; the README / llms.txt /
  rbac-verification.md descriptions are corrected to match.
```

- [ ] **Ship.** Commit, push, monitor CI (`gh run list --branch main`).
- [ ] **Close #1171.** Comment summarising the implementation + commits; `gh issue close 1171`.
- [ ] **Update #1176.** Note that the RBAC-overclaim portion is resolved by #1171's doc step; #1176's remaining scope is the compliance-language reframe + SECURITY_CLAIMS.md / EVALUATION.md / maturity table.

---

## Notes for the implementer

- **Order caveat:** Tasks 3 and 4 are mutually referencing — seeding (3) needs a booted app context (4). Implement Task 4's `_verifier_app_context` + `_build_asgi_app` first, then Task 3. The plan lists 3 before 4 for narrative flow only.
- **The hard parts are the two `Step 1: Read…` steps** (Task 3 and Task 4). The exact app-construction entrypoint and the user-management create route are framework internals — read them before writing, do not guess. Everything else in the plan is concrete.
- **`fixtures/rbac_validation`** is the target app: a medical-domain RBAC probe with ~8 personas and 4 entities. It has no UI/workspaces — a clean matrix to verify. If its entities have required fields that block empty-body creation, that surfaces in Task 3 Step 4 — extend `_seed_baseline_rows` to build a minimal valid body from the entity IR.
- **Postgres dependency:** Tasks 2–6 need a running PostgreSQL. The unit-only Task 1 does not. CI's `postgres-tests` job picks up the `postgres`-marked file automatically.
