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

#1313 slice 1b will extend this fixture with a guarded ``atomic`` reassign
flow once the per-step in-transaction scope enforcement lands.
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

    def __init__(self, transport: Any, db_url: str) -> None:
        self._transport = transport
        self._db_url = db_url
        self.creds: dict[str, tuple[str, str]] = {}  # role-key -> (email, password)
        # Seeded ids the tests reference.
        self.math_dept_id = ""
        self.science_dept_id = ""
        self.math_group_id = ""
        self.math_group2_id = ""
        self.science_group_id = ""
        self.math_enrolment_id = ""

    async def client_as(self, who: str) -> httpx.AsyncClient:
        import httpx

        from dazzle.cli.rbac import _login

        email, password = self.creds[who]
        client = httpx.AsyncClient(
            transport=self._transport, base_url=_BASE_URL, follow_redirects=True
        )
        await _login(client, _BASE_URL, email, password)
        return client


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
        app = _ScopeRuntimeApp(transport=transport, db_url=db_url)
        _seed(app, auth_store, db_url)
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
