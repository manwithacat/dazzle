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
        # #1318 — flow-level invariant anchor (a Transaction) + its seeded
        # counter-posting amount (the flow appends the balancing posting).
        self.txn_id = ""

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
    app.txn_id = _mk_id()

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
        # A science-department enrolment — used by the atomic-reassign
        # source-check test (a maths teacher must not touch it).
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
        # #1318 — a Transaction anchor + a seeded posting of -5. The
        # `balanced_post` flow appends one posting; the transaction's postings
        # must net to zero. The test passes a=5 (balanced → commits) or a≠5
        # (unbalanced → rolls back).
        _sql_insert(conn, "Transaction", {"id": app.txn_id, "label": "Ledger txn"})
        _sql_insert(
            conn,
            "Posting",
            {"id": _mk_id(), "transaction": app.txn_id, "amount": -5},
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
# #1313 slice 1b — per-step `scope: create:` enforcement inside an atomic flow
# (in-transaction probe), against real Postgres
# ---------------------------------------------------------------------------


async def _atomic_enrol(app: _ScopeRuntimeApp, who: str, *, label: str, group_id: str) -> Any:
    client = await app.client_as(who)
    return await _csrf_post(
        client, "/api/atomic/enrol_student", {"label": label, "group": group_id}
    )


async def test_atomic_create_in_own_department_is_allowed(app: _ScopeRuntimeApp) -> None:
    """A teacher's atomic enrol into an own-department group satisfies the
    per-step `scope: create:` (FK-path) and commits."""
    resp = await _atomic_enrol(
        app, "teacher_math", label="Atomic maths", group_id=app.math_group_id
    )
    assert resp.status_code < 400, (
        f"own-dept atomic enrol should succeed, got {resp.status_code}: {resp.text[:300]}"
    )


async def test_atomic_create_in_foreign_department_is_denied_and_rolls_back(
    app: _ScopeRuntimeApp,
) -> None:
    """A teacher's atomic enrol into a foreign-department group is denied (403)
    by the in-transaction per-step scope probe, and the flow rolls back — the
    raw-INSERT-bypasses-scope hole is closed."""
    resp = await _atomic_enrol(
        app, "teacher_math", label="Atomic smuggle", group_id=app.science_group_id
    )
    assert resp.status_code == 403, (
        f"foreign-dept atomic enrol should 403, got {resp.status_code}: {resp.text[:300]}"
    )

    # Roll-back check: the denied enrolment must not have been persisted.
    import psycopg

    with psycopg.connect(app._db_url) as conn:
        cur = conn.cursor()
        cur.execute('SELECT count(*) FROM "Enrolment" WHERE "label" = %s', ["Atomic smuggle"])
        assert cur.fetchone()[0] == 0, "denied atomic create must not persist any row"


async def test_atomic_create_admin_unrestricted(app: _ScopeRuntimeApp) -> None:
    resp = await _atomic_enrol(
        app, "admin", label="Atomic admin cross-dept", group_id=app.science_group_id
    )
    assert resp.status_code < 400, (
        f"admin atomic enrol should succeed, got {resp.status_code}: {resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# #1317 — strict in-transaction audit (the `enrol_student_strict` flow,
# `audit: strict`): the audit row is written to `_dazzle_atomic_audit` on the
# flow's own connection, so it commits with the mutation and rolls back with it.
# ---------------------------------------------------------------------------


async def _atomic_enrol_strict(app: _ScopeRuntimeApp, who: str, *, label: str, group_id: str):
    client = await app.client_as(who)
    return await _csrf_post(
        client, "/api/atomic/enrol_student_strict", {"label": label, "group": group_id}
    )


def _atomic_audit_rows(db_url: str, flow: str | None = None) -> list[dict[str, Any]]:
    """Read `_dazzle_atomic_audit`; tolerate the table not existing.

    The booted app (scope_runtime declares `enrol_student_strict`) creates the
    side-table once at boot (#1317), so it normally exists with zero or more
    rows; the UndefinedTable tolerance is a defensive fallback.
    """
    import psycopg
    from psycopg.rows import dict_row

    try:
        with psycopg.connect(db_url, row_factory=dict_row) as conn:
            cur = conn.cursor()
            if flow:
                cur.execute("SELECT * FROM _dazzle_atomic_audit WHERE flow_name = %s", [flow])
            else:
                cur.execute("SELECT * FROM _dazzle_atomic_audit")
            return list(cur.fetchall())
    except psycopg.errors.UndefinedTable:
        return []


async def test_strict_atomic_audit_row_commits_with_the_mutation(
    app: _ScopeRuntimeApp,
) -> None:
    """An own-dept strict enrol commits, and exactly one in-transaction audit
    row lands in `_dazzle_atomic_audit` — atomic with the INSERT."""
    resp = await _atomic_enrol_strict(
        app, "teacher_math", label="Strict maths", group_id=app.math_group_id
    )
    assert resp.status_code < 400, (
        f"own-dept strict enrol should succeed, got {resp.status_code}: {resp.text[:300]}"
    )

    rows = _atomic_audit_rows(app._db_url, flow="enrol_student_strict")
    assert len(rows) == 1, f"expected exactly one strict-audit row, got {len(rows)}"
    row = rows[0]
    assert row["decision"] == "allow"
    assert row["operation"] == "create"
    assert row["entity_name"] == "Enrolment"
    assert row["matched_policy"] == "atomic:enrol_student_strict"
    assert row["entity_id"]  # the committed Enrolment id


async def test_strict_atomic_audit_rolls_back_with_a_denied_flow(
    app: _ScopeRuntimeApp,
) -> None:
    """A foreign-dept strict enrol is denied (403) and rolls back — NO audit row
    is left behind (the in-transaction write rolls back with the mutation),
    proving the strict audit is atomic, not best-effort."""
    resp = await _atomic_enrol_strict(
        app, "teacher_math", label="Strict smuggle", group_id=app.science_group_id
    )
    assert resp.status_code == 403, (
        f"foreign-dept strict enrol should 403, got {resp.status_code}: {resp.text[:300]}"
    )

    assert _atomic_audit_rows(app._db_url, flow="enrol_student_strict") == [], (
        "a denied/rolled-back strict flow must leave no audit row"
    )

    import psycopg

    with psycopg.connect(app._db_url) as conn:
        cur = conn.cursor()
        cur.execute('SELECT count(*) FROM "Enrolment" WHERE "label" = %s', ["Strict smuggle"])
        assert cur.fetchone()[0] == 0, "denied strict flow must not persist the Enrolment either"


# ---------------------------------------------------------------------------
# #1313 — atomic `update` step execution + scope: update: (source + destination)
# in-transaction, against real Postgres
# ---------------------------------------------------------------------------


async def _atomic_reassign(
    app: _ScopeRuntimeApp, who: str, *, enrolment_id: str, group_id: str
) -> Any:
    client = await app.client_as(who)
    return await _csrf_post(
        client,
        "/api/atomic/reassign_enrolment",
        {"enrolment": enrolment_id, "group": group_id},
    )


async def test_atomic_reassign_within_department_is_allowed(app: _ScopeRuntimeApp) -> None:
    """Moving an own-department enrolment to another own-department group passes
    both the source and destination scope: update: checks."""
    resp = await _atomic_reassign(
        app, "teacher_math", enrolment_id=app.math_enrolment_id, group_id=app.math_group2_id
    )
    assert resp.status_code < 400, (
        f"in-dept reassign should succeed, got {resp.status_code}: {resp.text[:300]}"
    )


async def test_atomic_reassign_to_foreign_department_is_denied(app: _ScopeRuntimeApp) -> None:
    """Reassigning an own enrolment to a foreign-department group fails the
    DESTINATION check → 404 + rollback (group unchanged)."""
    resp = await _atomic_reassign(
        app, "teacher_math", enrolment_id=app.math_enrolment_id, group_id=app.science_group_id
    )
    assert resp.status_code == 404, (
        f"foreign-dept reassign should 404, got {resp.status_code}: {resp.text[:300]}"
    )
    import psycopg

    with psycopg.connect(app._db_url) as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT "teaching_group" FROM "Enrolment" WHERE "id" = %s', [app.math_enrolment_id]
        )
        assert str(cur.fetchone()[0]) == app.math_group_id, (
            "denied reassign must not change the row"
        )


async def test_atomic_reassign_of_foreign_source_is_denied(app: _ScopeRuntimeApp) -> None:
    """A maths teacher must not touch a science-department enrolment even when
    moving it INTO maths — the SOURCE check (the row they can't see) denies it."""
    resp = await _atomic_reassign(
        app, "teacher_math", enrolment_id=app.science_enrolment_id, group_id=app.math_group_id
    )
    assert resp.status_code == 404, (
        f"foreign-source reassign should 404, got {resp.status_code}: {resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# #1313 — audit fact per committed atomic step (ADR-0029 invariant 5,
# async-enqueue), against real Postgres
# ---------------------------------------------------------------------------


async def test_atomic_commit_writes_audit_fact(app: _ScopeRuntimeApp) -> None:
    """A committed atomic create writes an `allow` audit row for the touched
    entity, correlated by flow name (`atomic:enrol_student`)."""
    resp = await _atomic_enrol(
        app, "teacher_math", label="Audited maths", group_id=app.math_group_id
    )
    assert resp.status_code < 400, resp.text[:300]
    rows = app.audit_rows(matched_policy="atomic:enrol_student")
    assert rows, "a committed atomic create must write an audit fact"
    row = rows[0]
    assert row["operation"] == "create"
    assert row["entity_name"] == "Enrolment"
    assert row["decision"] == "allow"


async def test_denied_atomic_flow_writes_no_audit_fact(app: _ScopeRuntimeApp) -> None:
    """A scope-denied atomic flow rolls back and records no audit fact for the
    denied step (nothing committed ⇒ nothing to record)."""
    resp = await _atomic_enrol(
        app, "teacher_math", label="Denied audit", group_id=app.science_group_id
    )
    assert resp.status_code == 403, resp.text[:300]
    rows = app.audit_rows(matched_policy="atomic:enrol_student")
    assert rows == [], "a denied/rolled-back atomic flow must not write an audit fact"


# ---------------------------------------------------------------------------
# #1318 — flow-level aggregate invariant (ADR-0031): the `balanced_post` flow
# appends a Posting and asserts the transaction's postings net to zero at
# commit. A balanced set commits; an unbalanced set rolls the whole flow back
# (400). The seed leaves one posting of -5 on the transaction, so a=5 balances.
# ---------------------------------------------------------------------------


async def _atomic_balanced_post(app: _ScopeRuntimeApp, who: str, *, txn_id: str, a: int) -> Any:
    client = await app.client_as(who)
    return await _csrf_post(client, "/api/atomic/balanced_post", {"txn": txn_id, "a": a})


def _posting_count(db_url: str, txn_id: str) -> int:
    import psycopg

    with psycopg.connect(db_url) as conn:
        cur = conn.cursor()
        cur.execute('SELECT count(*) FROM "Posting" WHERE "transaction" = %s', [txn_id])
        return int(cur.fetchone()[0])


async def test_invariant_balanced_commits(app: _ScopeRuntimeApp) -> None:
    """Seed posting -5 + flow posting +5 ⇒ sum 0 ⇒ the invariant holds and the
    flow commits (the appended posting persists)."""
    before = _posting_count(app._db_url, app.txn_id)
    resp = await _atomic_balanced_post(app, "admin", txn_id=app.txn_id, a=5)
    assert resp.status_code < 400, (
        f"balanced post should commit, got {resp.status_code}: {resp.text[:300]}"
    )
    assert _posting_count(app._db_url, app.txn_id) == before + 1, (
        "a balanced post must persist the appended posting"
    )


async def test_invariant_unbalanced_rolls_back(app: _ScopeRuntimeApp) -> None:
    """Seed posting -5 + flow posting +3 ⇒ sum -2 ≠ 0 ⇒ the invariant is violated,
    the flow rolls back (400), and the appended posting is NOT persisted."""
    before = _posting_count(app._db_url, app.txn_id)
    resp = await _atomic_balanced_post(app, "admin", txn_id=app.txn_id, a=3)
    assert resp.status_code == 400, (
        f"unbalanced post should 400, got {resp.status_code}: {resp.text[:300]}"
    )
    assert _posting_count(app._db_url, app.txn_id) == before, (
        "a violated invariant must roll back the appended posting"
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
