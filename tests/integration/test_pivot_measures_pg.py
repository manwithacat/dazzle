"""Real-Postgres proof that a multi-measure pivot stays one qualified GROUP BY (#1800).

A ``pivot_table`` over two FK dimensions (question × class) LEFT JOINs both
targets for labels. Its measures — ``avg(score)``, ``avg(max_score)``, an L3
``avg(score::float / nullif(max_score, 0))`` and a derived
``round(awarded / available * 100)`` facility percentage — must all ride that
one query with every measure column qualified by the source table: ``Klass``
carries its own ``score`` so an unqualified measure is ``column reference
"score" is ambiguous`` (#1791 detector kept live), which the pivot logs as
"Pivot aggregate FAILED" and renders empty.

Boots a copy of ``fixtures/scope_runtime`` in ``tmp_path`` (no ``xdist_group``
pin needed) and reads the region as the admin.
"""

from __future__ import annotations

import logging
import os
import re
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
_PASSWORD = "pivot-measures-password"  # nosec B105 — disposable scratch DB only
_ADMIN = "admin@scope.test"

# `score` exists on BOTH Klass (an FK target) and MarkingResult (the source).
_PIVOT_DSL = """

entity Klass "Class":
  id: uuid pk
  name: str(120) required
  score: int

  permit:
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


entity Question "Question":
  id: uuid pk
  name: str(120) required

  permit:
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


entity MarkingResult "Marking Result":
  id: uuid pk
  klass: ref Klass required
  question: ref Question required
  department: ref Department required
  score: int
  max_score: int

  permit:
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


workspace mock_review "Mock Review":
  purpose: "Facility index by question and class"
  access: persona(admin)

  facility_index:
    source: MarkingResult
    display: pivot_table
    group_by: [question, klass]
    aggregate:
      awarded: avg(score)
      available: avg(max_score)
      facility_ratio: avg(score::float / nullif(max_score, 0))
      facility_pct: round(awarded / available * 100)
    empty: "No marks yet"
"""

_PIVOT_FAILED = "Pivot aggregate FAILED"
_PIVOT_SKIPPED = "skipped the pivot"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_pivot_measures"
    shutil.copytree(_FIXTURE, root)
    domain = root / "dsl" / "domain.dsl"
    domain.write_text(domain.read_text() + _PIVOT_DSL)
    return root


def _insert(conn: Any, table: str, row: dict[str, Any]) -> None:
    """Table/column names are hardcoded DSL constants; values are parameterised."""
    cols = ", ".join(f'"{k}"' for k in row)
    placeholders = ", ".join("%s" for _ in row)
    conn.execute(  # nosemgrep — constant identifiers, param values
        f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})', list(row.values())
    )


class _App:
    def __init__(self, transport: Any, db_url: str) -> None:
        self.transport = transport
        self.db_url = db_url
        self.maths = str(uuid.uuid4())
        self.klass_7a = str(uuid.uuid4())
        self.klass_7b = str(uuid.uuid4())
        self.q1 = str(uuid.uuid4())
        self.q2 = str(uuid.uuid4())


def _seed(app: _App, auth_store: Any) -> None:
    import psycopg

    if auth_store.get_user_by_email(_ADMIN) is None:
        auth_store.create_user(_ADMIN, _PASSWORD, roles=["admin"])
    with psycopg.connect(app.db_url) as conn:
        _insert(conn, "Department", {"id": app.maths, "name": "Maths"})
        # Klass.score is far from any cell value: a measure resolved to the
        # FK target would show 900 / 800.
        _insert(conn, "Klass", {"id": app.klass_7a, "name": "Class 7A", "score": 900})
        _insert(conn, "Klass", {"id": app.klass_7b, "name": "Class 7B", "score": 800})
        _insert(conn, "Question", {"id": app.q1, "name": "Question 1"})
        _insert(conn, "Question", {"id": app.q2, "name": "Question 2"})
        # Q1×7A: avg 4/8 → 50%; Q1×7B: 6/8 → 75%; Q2×7A: 9/10 → 90%.
        for klass, question, score, max_score in (
            (app.klass_7a, app.q1, 5, 8),
            (app.klass_7a, app.q1, 3, 8),
            (app.klass_7b, app.q1, 6, 8),
            (app.klass_7a, app.q2, 9, 10),
        ):
            _insert(
                conn,
                "MarkingResult",
                {
                    "id": str(uuid.uuid4()),
                    "klass": klass,
                    "question": question,
                    "department": app.maths,
                    "score": score,
                    "max_score": max_score,
                },
            )
        conn.commit()


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[_App]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase, _probe_transport

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(_project(tmp_path), db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "scope_runtime has auth enabled"
        a = _App(_probe_transport(httpx.ASGITransport(app=built.app)), db_url)
        _seed(a, auth_store)
        try:
            yield a
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


async def _region(app: _App, workspace: str, region: str, **params: str) -> str:
    import httpx

    from dazzle.cli.rbac import _login

    async with httpx.AsyncClient(
        transport=app.transport, base_url=_BASE_URL, follow_redirects=True
    ) as client:
        await _login(client, _BASE_URL, _ADMIN, _PASSWORD)
        resp = await client.get(f"/api/workspaces/{workspace}/regions/{region}", params=params)
    assert resp.status_code == 200, f"{region}: {resp.status_code} {resp.text[:400]}"
    return resp.text


def _numbers(body: str) -> set[str]:
    """Bare numeric text nodes — parsed loosely so markup churn doesn't break the gate."""
    return set(re.findall(r">\s*(\d+(?:\.\d+)?)\s*<", body))


async def test_pivot_measures_ride_one_qualified_group_by(
    app: _App, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    body = await _region(app, "mock_review", "facility_index")

    messages = [r.getMessage() for r in caplog.records]
    assert not [m for m in messages if _PIVOT_FAILED in m], "pivot query failed (ambiguous column?)"
    assert not [m for m in messages if _PIVOT_SKIPPED in m], "a measure was skipped"
    for label in ("Question 1", "Question 2", "Class 7A", "Class 7B"):
        assert label in body, f"missing pivot label {label!r}: {body[:600]!r}"
    nums = _numbers(body)
    assert {"50", "75", "90"} <= nums, f"facility percentages per cell: {nums}"
    assert {"0.5", "0.75", "0.9"} <= nums, f"L3 ratio measure per cell: {nums}"
    assert {"4", "6", "9"} <= nums, f"avg(score) per cell: {nums}"
    assert not {"900", "800", "850"} & nums, "measure resolved to the FK target's column"
