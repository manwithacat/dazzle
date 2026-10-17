"""Real-Postgres proof that a grouped FK aggregate stays unambiguous (#1791).

A ``group_by: <fk>`` region LEFT JOINs the FK target to label its buckets. When
the target shares column names with the source (here ``Klass.score`` next to
``CohortAnalysis.score``, and ``department`` on both), the measure and the region
``filter:`` column must be qualified with the source table — otherwise Postgres
raises ``column reference "score" is ambiguous``, the grouped query fails (logged
as "GROUP BY aggregate failed") and the comparison used to fall back to ranking
raw source rows labelled ``{'id': UUID(...), '__display__': ...}``.

Unit tests pin the SQL strings; only a real Postgres catches the ambiguity, so
this is the live detector the class lacked. It boots a copy of
``fixtures/scope_runtime`` with a target ``Klass`` and a source ``CohortAnalysis``
appended, seeds two classes in two departments, and reads two ``display:
comparison`` regions as the admin — an ``avg(score)`` league (measure
ambiguity) and a ``count`` league narrowed by a ``department = current_context``
region filter (filter ambiguity, isolated: ``COUNT(*)`` names no column).

The copy lives in ``tmp_path``, so no ``xdist_group`` pin is needed.
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
_PASSWORD = "grouped-fk-aggregate-password"  # nosec B105 — disposable scratch DB only
_ADMIN = "admin@scope.test"

# `score` and `department` exist on BOTH Klass (the FK target) and
# CohortAnalysis (the source) — the AegisMark collision shape.
_GROUPED_DSL = """

entity Klass "Class":
  id: uuid pk
  name: str(120) required
  department: ref Department required
  score: int

  permit:
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


entity CohortAnalysis "Cohort Analysis":
  id: uuid pk
  klass: ref Klass required
  department: ref Department required
  score: int

  permit:
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


workspace cohort_board "Cohort Board":
  purpose: "Rank classes by mean score"
  access: persona(admin)

  class_league:
    source: CohortAnalysis
    display: comparison
    group_by: klass
    aggregate:
      mean_score: avg(score)
    rank_by: mean_score
    order: desc
    empty: "No cohort analyses"


workspace department_cohort "Department Cohort":
  purpose: "Rank one department's classes by mean score"
  access: persona(admin)

  context_selector:
    entity: Department
    display_field: name

  # COUNT(*) names no column, so this region isolates the filter defect:
  # only `department = current_context` can collide with Klass.department.
  department_league:
    source: CohortAnalysis
    filter: department = current_context
    display: comparison
    group_by: klass
    aggregate:
      analyses: count(CohortAnalysis)
    rank_by: analyses
    order: desc
    empty: "No cohort analyses in this department"
"""

# Logged by workspace_aggregation when the grouped query raises.
_GROUPED_FAILED = "GROUP BY aggregate failed"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_grouped_fk_aggregate"
    shutil.copytree(_FIXTURE, root)
    domain = root / "dsl" / "domain.dsl"
    domain.write_text(domain.read_text() + _GROUPED_DSL)
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
        self.science = str(uuid.uuid4())
        self.klass_7a = str(uuid.uuid4())
        self.klass_7b = str(uuid.uuid4())


def _seed(app: _App, auth_store: Any) -> None:
    import psycopg

    if auth_store.get_user_by_email(_ADMIN) is None:
        auth_store.create_user(_ADMIN, _PASSWORD, roles=["admin"])
    with psycopg.connect(app.db_url) as conn:
        _insert(conn, "Department", {"id": app.maths, "name": "Maths"})
        _insert(conn, "Department", {"id": app.science, "name": "Science"})
        # Klass.score is deliberately far from the source averages: an
        # unqualified measure that resolved to the target would show 900 / 800.
        _insert(
            conn,
            "Klass",
            {"id": app.klass_7a, "name": "Class 7A", "department": app.maths, "score": 900},
        )
        _insert(
            conn,
            "Klass",
            {"id": app.klass_7b, "name": "Class 7B", "department": app.science, "score": 800},
        )
        for klass, dept, score in (
            (app.klass_7a, app.maths, 10),
            (app.klass_7a, app.maths, 20),
            (app.klass_7b, app.science, 40),
        ):
            _insert(
                conn,
                "CohortAnalysis",
                {"id": str(uuid.uuid4()), "klass": klass, "department": dept, "score": score},
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


def _assert_no_dict_labels(body: str) -> None:
    for leak in ("UUID(", "__display__", "{'id'", "{&#x27;id&#x27;", "{&#39;id&#39;"):
        assert leak not in body, f"FK dict repr leaked into the comparison ({leak!r}): {body!r}"


def _grouped_failures(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if _GROUPED_FAILED in r.getMessage()]


def _numbers(body: str) -> set[str]:
    """Bare numeric text nodes — parsed loosely so markup churn doesn't break the gate."""
    return set(re.findall(r">\s*(\d+(?:\.\d+)?)\s*<", body))


async def test_grouped_fk_comparison_qualifies_measure(
    app: _App, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    body = await _region(app, "cohort_board", "class_league")

    assert _grouped_failures(caplog) == [], "grouped query hit an ambiguous column"
    _assert_no_dict_labels(body)
    assert "Class 7A" in body and "Class 7B" in body
    assert body.index("Class 7B") < body.index("Class 7A"), "ranked desc by mean score"
    nums = _numbers(body)
    assert {"15", "40"} <= nums or {"15.0", "40.0"} <= nums, f"real averages: {nums}"
    assert not {"900", "800"} & nums, "measure resolved to the FK target's column"


async def test_grouped_fk_comparison_qualifies_region_filter(
    app: _App, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    body = await _region(app, "department_cohort", "department_league", context_id=app.maths)

    assert _grouped_failures(caplog) == [], "grouped query hit an ambiguous column"
    _assert_no_dict_labels(body)
    assert "Class 7A" in body
    assert "Class 7B" not in body, "department = current_context must narrow the GROUP BY"
    assert "2" in _numbers(body), "Maths has two analyses, both for Class 7A"
