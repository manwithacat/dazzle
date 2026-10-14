"""Real-Postgres runtime verification for the scope-enforcement tools.

Boots the ``fixtures/scope_runtime`` framework fixture in-process against a
disposable PostgreSQL database and exercises, over HTTP, the scope tools that
are otherwise only unit-tested with an injected fake probe:

* **#1311 — FK-path (depth-2) `scope: create:`** via the payload-time SQL
  probe. A teacher may create an ``Enrolment`` only when its ``teaching_group``
  is in the teacher's own department; a group in a foreign department is
  rejected (403). This is the test that proves the probe runs correctly
  against real SQL (str→uuid coercion, the ``EXISTS (… "id" = %s …)`` shape,
  tenant search_path), not just against a fake.

* **#1312 — `scope: update:` DESTINATION revalidation.** Repointing an
  in-scope enrolment's ``teaching_group`` to a group in a foreign department
  must 404 (the would-be-final row fails scope); repointing within the
  department succeeds.

Marked ``postgres`` (+ ``e2e``): skipped locally without
``TEST_DATABASE_URL`` / ``DATABASE_URL``; CI's ``postgres-tests`` job runs it
against a real ``postgres:16`` service.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import httpx

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/scope_runtime")
_BASE_URL = "http://scope-runtime.local"
_PASSWORD = "scope-test-password"  # nosec B105 — disposable scratch DB only


def _mk_id() -> str:
    return str(uuid.uuid4())


def _sql_insert(conn: Any, table: str, row: dict[str, Any]) -> None:
    """Insert one row. Table/column names are hardcoded DSL constants (not user
    input); values go through %s parameterisation."""
    cols = ", ".join(f'"{k}"' for k in row)
    placeholders = ", ".join("%s" for _ in row)
    sql = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})'
    conn.execute(sql, list(row.values()))  # nosemgrep — constant identifiers, param values


class _ScopeRuntimeApp:
    """Boots scope_runtime + holds seeded ids and per-role client factories."""

    def __init__(self, transport: Any, db_url: str, audit_logger: Any = None) -> None:
        self._transport = transport
        self._db_url = db_url
        self._audit_logger = audit_logger
        self.creds: dict[str, tuple[str, str]] = {}  # role-key -> (email, password)
        # Seeded ids the tests reference.
        self.math_dept_id = ""
        self.science_dept_id = ""
        self.math_group_id = ""
        self.math_group2_id = ""
        self.science_group_id = ""
        self.math_enrolment_id = ""
        self.science_enrolment_id = ""

    async def client_as(self, who: str) -> httpx.AsyncClient:
        import httpx

        from dazzle.cli.rbac import _login

        email, password = self.creds[who]
        client = httpx.AsyncClient(
            transport=self._transport, base_url=_BASE_URL, follow_redirects=True
        )
        await _login(client, _BASE_URL, email, password)
        return client

    def audit_rows(self, **where: str) -> list[dict[str, Any]]:
        """Flush the async audit queue, then query _dazzle_audit_log."""
        if self._audit_logger is not None:
            self._audit_logger.drain()
        import psycopg
        from psycopg.rows import dict_row

        clause = " AND ".join(f"{k} = %s" for k in where)
        sql = "SELECT * FROM _dazzle_audit_log"
        if clause:
            sql += f" WHERE {clause}"  # nosemgrep — keys are test-controlled column names
        with psycopg.connect(self._db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(where.values()))
                return list(cur.fetchall())


async def _csrf_post(client: httpx.AsyncClient, url: str, body: dict[str, Any]) -> httpx.Response:
    token = client.cookies.get("dazzle_csrf")
    headers = {"X-CSRF-Token": token} if token else {}
    return await client.post(url, json=body, headers=headers)


async def _csrf_put(client: httpx.AsyncClient, url: str, body: dict[str, Any]) -> httpx.Response:
    token = client.cookies.get("dazzle_csrf")
    headers = {"X-CSRF-Token": token} if token else {}
    return await client.put(url, json=body, headers=headers)


def _seed(app: _ScopeRuntimeApp, auth_store: Any, db_url: str) -> None:
    import psycopg

    # --- auth users (email == domain User email so current_user resolves) ----
    users = {
        "teacher_math": ("teacher.math@scope.test", "teacher"),
        "teacher_science": ("teacher.science@scope.test", "teacher"),
        "admin": ("admin@scope.test", "admin"),
        # Flense ship AA: a teacher with no domain User row, so
        # `current_user.department` does not resolve for them.
        "teacher_no_department": ("teacher.nodept@scope.test", "teacher"),
    }
    for key, (email, role) in users.items():
        if auth_store.get_user_by_email(email) is None:
            auth_store.create_user(email, _PASSWORD, roles=[role])
        app.creds[key] = (email, _PASSWORD)

    app.math_dept_id = _mk_id()
    app.science_dept_id = _mk_id()
    app.math_group_id = _mk_id()
    app.math_group2_id = _mk_id()
    app.science_group_id = _mk_id()
    app.math_enrolment_id = _mk_id()
    app.science_enrolment_id = _mk_id()

    with psycopg.connect(db_url) as conn:
        _sql_insert(conn, "Department", {"id": app.math_dept_id, "name": "Mathematics"})
        _sql_insert(conn, "Department", {"id": app.science_dept_id, "name": "Science"})

        # domain User rows — department FK drives current_user.department.
        _sql_insert(
            conn,
            "User",
            {
                "id": _mk_id(),
                "email": "teacher.math@scope.test",
                "name": "Maths Teacher",
                "department": app.math_dept_id,
            },
        )
        _sql_insert(
            conn,
            "User",
            {
                "id": _mk_id(),
                "email": "teacher.science@scope.test",
                "name": "Science Teacher",
                "department": app.science_dept_id,
            },
        )
        _sql_insert(
            conn,
            "User",
            {
                "id": _mk_id(),
                "email": "admin@scope.test",
                "name": "Admin",
                "department": app.math_dept_id,
            },
        )

        _sql_insert(
            conn,
            "TeachingGroup",
            {"id": app.math_group_id, "name": "Algebra", "department": app.math_dept_id},
        )
        _sql_insert(
            conn,
            "TeachingGroup",
            {"id": app.math_group2_id, "name": "Geometry", "department": app.math_dept_id},
        )
        _sql_insert(
            conn,
            "TeachingGroup",
            {"id": app.science_group_id, "name": "Physics", "department": app.science_dept_id},
        )

        _sql_insert(
            conn,
            "Enrolment",
            {
                "id": app.math_enrolment_id,
                "label": "Existing maths enrolment",
                "teaching_group": app.math_group_id,
                "status": "active",
            },
        )
        # A science-department enrolment (a maths teacher must not see it).
        _sql_insert(
            conn,
            "Enrolment",
            {
                "id": app.science_enrolment_id,
                "label": "Existing science enrolment",
                "teaching_group": app.science_group_id,
                "status": "active",
            },
        )
        conn.commit()


async def _booted() -> AsyncIterator[_ScopeRuntimeApp]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase, _probe_transport

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(_PROJECT_ROOT, db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "scope_runtime has auth enabled"
        transport = _probe_transport(httpx.ASGITransport(app=built.app))
        app = _ScopeRuntimeApp(
            transport=transport,
            db_url=db_url,
            audit_logger=getattr(built.builder, "audit_logger", None),
        )
        _seed(app, auth_store, db_url)
        # #1422: expose the builder (in-process create invokers) + auth_store + the
        # ASGI app so the create-invoker parity test can drive the in-process path.
        app.builder = built.builder
        app.auth_store = auth_store
        app.asgi_app = built.app
        try:
            yield app
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


@pytest.fixture
async def app() -> AsyncIterator[_ScopeRuntimeApp]:
    async for a in _booted():
        yield a


# ---------------------------------------------------------------------------
# #1311 — FK-path (depth-2) create-scope, against real Postgres
# ---------------------------------------------------------------------------


async def test_create_in_own_department_is_allowed(app: _ScopeRuntimeApp) -> None:
    client = await app.client_as("teacher_math")
    resp = await _csrf_post(
        client, "/enrolments", {"label": "Maths enrolment", "teaching_group": app.math_group_id}
    )
    assert resp.status_code < 400, (
        f"own-dept create should succeed, got {resp.status_code}: {resp.text[:300]}"
    )


async def test_create_in_foreign_department_is_denied(app: _ScopeRuntimeApp) -> None:
    """The FK-path probe resolves the group's department against the DB and
    rejects a teacher creating into another department — the spoof #1311 closes."""
    client = await app.client_as("teacher_math")
    resp = await _csrf_post(
        client,
        "/enrolments",
        {"label": "Cross-dept enrolment", "teaching_group": app.science_group_id},
    )
    assert resp.status_code == 403, (
        f"foreign-dept create should 403, got {resp.status_code}: {resp.text[:300]}"
    )


async def test_admin_create_unrestricted(app: _ScopeRuntimeApp) -> None:
    client = await app.client_as("admin")
    resp = await _csrf_post(
        client,
        "/enrolments",
        {"label": "Admin cross-dept enrolment", "teaching_group": app.science_group_id},
    )
    assert resp.status_code < 400, (
        f"admin create should succeed, got {resp.status_code}: {resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# #1312 — update DESTINATION revalidation, against real Postgres
# ---------------------------------------------------------------------------


async def test_update_within_department_is_allowed(app: _ScopeRuntimeApp) -> None:
    client = await app.client_as("teacher_math")
    resp = await _csrf_put(
        client,
        f"/enrolments/{app.math_enrolment_id}",
        {"label": "Moved to Geometry", "teaching_group": app.math_group2_id, "status": "active"},
    )
    assert resp.status_code < 400, (
        f"in-dept repoint should succeed, got {resp.status_code}: {resp.text[:300]}"
    )


async def test_update_repoint_into_foreign_department_is_denied(app: _ScopeRuntimeApp) -> None:
    """Repointing the enrolment's group into a foreign department must 404 —
    the would-be-final row fails the update scope (the #1312 destination guard)."""
    client = await app.client_as("teacher_math")
    resp = await _csrf_put(
        client,
        f"/enrolments/{app.math_enrolment_id}",
        {
            "label": "Smuggle to Science",
            "teaching_group": app.science_group_id,
            "status": "active",
        },
    )
    assert resp.status_code == 404, (
        f"foreign-dept repoint should 404, got {resp.status_code}: {resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# #1422 — single-id READ scope enforcement through the relocated `gated_read`
# core. The REST detail route now delegates to `access.gated.gated_read`, and
# the page layer (detail/edit handlers) calls the SAME core in-process instead
# of self-fetching this endpoint. This locks the read-path `scope: read:`
# enforcement the relocation must preserve.
# ---------------------------------------------------------------------------


async def test_rest_read_respects_read_scope_via_gated_read(app: _ScopeRuntimeApp) -> None:
    """A teacher may read an enrolment in their own department but gets 404 for a
    foreign-department one — proving `gated_read` enforces `scope: read:`
    (teaching_group.department = current_user.department) on the single-id read
    path. The page layer now calls this same core in-process, so this transitively
    covers the page-layer read enforcement (page maps the denial → 404)."""
    client = await app.client_as("teacher_math")

    own = await client.get(f"/enrolments/{app.math_enrolment_id}")
    assert own.status_code == 200, f"own-department read should succeed: {own.text[:200]}"

    foreign = await client.get(f"/enrolments/{app.science_enrolment_id}")
    assert foreign.status_code == 404, (
        f"out-of-scope read must 404 (gated_read denies), got {foreign.status_code}"
    )


async def test_rest_list_respects_list_scope_via_gated_list(app: _ScopeRuntimeApp) -> None:
    """The REST list reads through the relocated `gated_list` core (#1422). A
    teacher's list returns only own-department enrolments (scope-filtered), not
    foreign-department ones — proving `gated_list` enforces `scope: list:`
    (teaching_group.department = current_user.department). The page table now
    calls this same core in-process."""
    client = await app.client_as("teacher_math")
    resp = await client.get("/enrolments")
    assert resp.status_code == 200, resp.text[:200]
    ids = {row["id"] for row in resp.json()["items"]}
    assert app.math_enrolment_id in ids, "own-department enrolment should be listed"
    assert app.science_enrolment_id not in ids, (
        "foreign-department enrolment must be scope-filtered out of the list"
    )


async def test_unresolvable_scope_attribute_denies_cleanly(app: _ScopeRuntimeApp) -> None:
    """Flense ship AA: a teacher whose user record has no `department` used to get
    a 500 (TypeError in the scope union) on the list. The rule now matches no
    rows: the list is an empty page and a single read is 404, the same shapes as
    "no scope rule matched"."""
    client = await app.client_as("teacher_no_department")

    listed = await client.get("/enrolments")
    assert listed.status_code == 200, listed.text[:300]
    assert listed.json()["items"] == []

    read = await client.get(f"/enrolments/{app.math_enrolment_id}")
    assert read.status_code == 404, read.text[:300]


async def test_anonymous_list_reads_no_rows_of_a_scoped_entity(app: _ScopeRuntimeApp) -> None:
    """Flense ship AA: with `require_auth_by_default` off (this harness boots in
    test mode) the list route let an anonymous caller through, and `gated_list`
    skipped both the permit gate and the scope merge for it, so it read every
    enrolment. It now gets an empty page, as the search routes give it (ship P)."""
    import httpx

    async with httpx.AsyncClient(
        transport=app._transport, base_url=_BASE_URL, follow_redirects=True
    ) as anon:
        resp = await anon.get("/enrolments")
    assert resp.status_code in (200, 401), resp.text[:300]
    if resp.status_code == 200:
        assert resp.json()["items"] == []


async def test_inprocess_create_invoker_enforces_create_scope(app: _ScopeRuntimeApp) -> None:
    """#1422 — the in-process CREATE invoker (used by the experience-form POST
    instead of a loopback self-fetch) runs the SAME enforced create path: a
    teacher may create an Enrolment in their own department but a foreign-department
    create is rejected by `scope: create:` (#1311 FK-path probe). Proves the
    in-process write path enforces create-scope identically to the REST create."""
    import pytest
    from fastapi import HTTPException
    from starlette.requests import Request

    invoker = app.builder.create_invokers.get("Enrolment")
    assert invoker is not None, "Enrolment should expose an in-process create invoker"

    user = app.auth_store.get_user_by_email("teacher.math@scope.test")
    session = app.auth_store.create_session(user)
    auth_ctx = app.auth_store.validate_session(session.id)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/enrolments",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 1),
        "app": app.asgi_app,
    }
    req = Request(scope)

    own = await invoker(
        auth_ctx,
        req,
        body={"label": "via invoker", "teaching_group": app.math_group_id, "status": "active"},
    )
    assert own is not None, "own-department create should succeed in-process"

    with pytest.raises(HTTPException) as exc:
        await invoker(
            auth_ctx,
            req,
            body={"label": "foreign", "teaching_group": app.science_group_id, "status": "active"},
        )
    assert exc.value.status_code == 403, "foreign-department create must be scope-denied (403)"
