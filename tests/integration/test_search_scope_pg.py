"""Real-Postgres proof that the search routes honour `scope: list:` (ship P).

Before ship P, ``GET /_dazzle/fts/{entity}`` looked the entity's access spec up
on ``AppSpec.cedar_access_specs`` — an attribute that does not exist — so it
applied no scope at all, and ``GET /_dazzle/search`` (the cross-entity ILIKE
fallback) had no auth dependency and no scope either. A user could search out
rows their list endpoint hides.

This boots a copy of ``fixtures/scope_runtime`` (Enrolment is list-scoped to
``teaching_group.department = current_user.department`` for teachers, ``all``
for admin) with a ``search on Enrolment:`` block and a ``ux: search:`` list
surface added, seeds one enrolment per department, and has a maths teacher, a
science teacher and an admin search the same term ("enrolment", which both
rows match). Each teacher must see only their own department's row; the admin
sees both; an anonymous caller sees none.

The copy lives in ``tmp_path``, so no ``xdist_group`` pin is needed.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "scope_runtime"
_BASE_URL = "http://scope-runtime.local"
_PASSWORD = "search-scope-password"  # nosec B105 — disposable scratch DB only

_SEARCH_DSL = """

search on Enrolment:
  fields: label
  tokenizer: english
"""


def _project_with_search(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_search"
    shutil.copytree(_FIXTURE, root)
    surfaces = root / "dsl" / "surfaces.dsl"
    text = surfaces.read_text()
    marker = '    field status "Status"\n\nsurface enrolment_create'
    assert marker in text, "scope_runtime surfaces.dsl changed shape"
    text = text.replace(
        marker,
        '    field status "Status"\n  ux:\n    search: label\n\nsurface enrolment_create',
        1,
    )
    surfaces.write_text(text + _SEARCH_DSL)
    return root


def _mk_id() -> str:
    return str(uuid.uuid4())


def _insert(conn: Any, table: str, row: dict[str, Any]) -> None:
    """Table/column names are hardcoded DSL constants; values are parameterised."""
    cols = ", ".join(f'"{k}"' for k in row)
    placeholders = ", ".join("%s" for _ in row)
    conn.execute(  # nosemgrep — constant identifiers, param values
        f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})', list(row.values())
    )


class _App:
    def __init__(self, transport: Any) -> None:
        self.transport = transport
        self.creds: dict[str, str] = {}
        self.math_enrolment_id = _mk_id()
        self.science_enrolment_id = _mk_id()

    async def client(self, who: str | None) -> Any:
        import httpx

        from dazzle.cli.rbac import _login

        client = httpx.AsyncClient(
            transport=self.transport, base_url=_BASE_URL, follow_redirects=True
        )
        if who is not None:
            await _login(client, _BASE_URL, self.creds[who], _PASSWORD)
        return client


def _seed(app: _App, auth_store: Any, db_url: str) -> None:
    import psycopg

    users = {
        "teacher_math": ("teacher.math@scope.test", "teacher"),
        "teacher_science": ("teacher.science@scope.test", "teacher"),
        "admin": ("admin@scope.test", "admin"),
    }
    for key, (email, role) in users.items():
        if auth_store.get_user_by_email(email) is None:
            auth_store.create_user(email, _PASSWORD, roles=[role])
        app.creds[key] = email

    math_dept, science_dept = _mk_id(), _mk_id()
    math_group, science_group = _mk_id(), _mk_id()
    with psycopg.connect(db_url) as conn:
        _insert(conn, "Department", {"id": math_dept, "name": "Mathematics"})
        _insert(conn, "Department", {"id": science_dept, "name": "Science"})
        for email, name, dept in (
            ("teacher.math@scope.test", "Maths Teacher", math_dept),
            ("teacher.science@scope.test", "Science Teacher", science_dept),
            ("admin@scope.test", "Admin", math_dept),
        ):
            _insert(
                conn, "User", {"id": _mk_id(), "email": email, "name": name, "department": dept}
            )
        _insert(
            conn, "TeachingGroup", {"id": math_group, "name": "Algebra", "department": math_dept}
        )
        _insert(
            conn,
            "TeachingGroup",
            {"id": science_group, "name": "Physics", "department": science_dept},
        )
        _insert(
            conn,
            "Enrolment",
            {
                "id": app.math_enrolment_id,
                "label": "Maths enrolment",
                "teaching_group": math_group,
                "status": "active",
            },
        )
        _insert(
            conn,
            "Enrolment",
            {
                "id": app.science_enrolment_id,
                "label": "Science enrolment",
                "teaching_group": science_group,
                "status": "active",
            },
        )
        conn.commit()


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[_App]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase, _probe_transport

    project = _project_with_search(tmp_path)
    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(project, db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "scope_runtime has auth enabled"
        a = _App(_probe_transport(httpx.ASGITransport(app=built.app)))
        _seed(a, auth_store, db_url)
        try:
            yield a
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


async def _fts_ids(app: _App, who: str) -> set[str]:
    client = await app.client(who)
    resp = await client.get("/_dazzle/fts/Enrolment", params={"q": "enrolment"})
    assert resp.status_code == 200, f"{who} FTS: {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    ids = {str(row["id"]) for row in body["items"]}
    assert body["total"] == len(ids), f"{who}: total must count only visible rows"
    return ids


async def _search_ids(app: _App, who: str | None) -> set[str]:
    client = await app.client(who)
    resp = await client.get("/_dazzle/search", params={"q": "enrolment", "limit": 50})
    assert resp.status_code == 200, f"{who} search: {resp.status_code} {resp.text[:300]}"
    ids: set[str] = set()
    for group in resp.json()["results"]:
        if group["entity"] == "Enrolment":
            ids |= {str(row["id"]) for row in group["items"]}
    return ids


async def test_fts_returns_only_rows_in_the_callers_scope(app: _App) -> None:
    both = {app.math_enrolment_id, app.science_enrolment_id}
    assert await _fts_ids(app, "teacher_math") == {app.math_enrolment_id}
    assert await _fts_ids(app, "teacher_science") == {app.science_enrolment_id}
    assert await _fts_ids(app, "admin") == both


async def test_cross_entity_search_returns_only_rows_in_the_callers_scope(app: _App) -> None:
    both = {app.math_enrolment_id, app.science_enrolment_id}
    assert await _search_ids(app, "teacher_math") == {app.math_enrolment_id}
    assert await _search_ids(app, "teacher_science") == {app.science_enrolment_id}
    assert await _search_ids(app, "admin") == both
    assert await _search_ids(app, None) == set(), "anonymous search must not read scoped rows"
