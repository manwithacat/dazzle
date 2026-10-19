"""Real-Postgres proof that ``start_of(period)`` is a calendar window (#1800).

``now - 7d`` slides with the clock; ``start_of(week)`` / ``start_of(month)``
pin the window to the first day of the current ISO week / month in the
tenant calendar. Boots a copy of ``fixtures/scope_runtime`` in ``tmp_path``
(no ``xdist_group`` pin needed), seeds marks just inside and just outside
each anchor, and reads two ``display: metrics`` regions as the admin — one
anchored in the aggregate ``where`` and one through the region ``filter:``.
Expectations derive from ``calendar_today()`` so the test holds on any day.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "scope_runtime"
_BASE_URL = "http://scope-runtime.local"
_PASSWORD = "calendar-anchor-password"  # nosec B105 — disposable scratch DB only
_ADMIN = "admin@scope.test"

_ANCHOR_DSL = """

entity Mark "Mark":
  id: uuid pk
  label: str(60) required
  marked_at: datetime required

  permit:
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


workspace hod_week "HoD Week":
  purpose: "Marking since Monday and this month"
  access: persona(admin)

  since_monday:
    source: Mark
    display: metrics
    aggregate:
      marked_this_week: count(Mark where marked_at >= start_of(week))
    empty: "No marks"

  this_month:
    source: Mark
    filter: marked_at >= start_of(month)
    display: metrics
    aggregate:
      marked_this_month: count(Mark)
    empty: "No marks"
"""


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_calendar_anchor"
    shutil.copytree(_FIXTURE, root)
    domain = root / "dsl" / "domain.dsl"
    domain.write_text(domain.read_text() + _ANCHOR_DSL)
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
        self.expected_week = 0
        self.expected_month = 0


def _seed(app: _App, auth_store: Any) -> None:
    import psycopg

    from dazzle.i18n.display_locale import calendar_today, get_display_locale

    if auth_store.get_user_by_email(_ADMIN) is None:
        auth_store.create_user(_ADMIN, _PASSWORD, roles=["admin"])
    today = calendar_today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    noon = time(12, 0, tzinfo=UTC)
    stamps = {
        "now": datetime.now(UTC),
        "before_monday": datetime.combine(week_start - timedelta(days=1), noon),
        "before_month": datetime.combine(month_start - timedelta(days=1), noon),
        "last_year": datetime.combine(today.replace(month=1, day=1) - timedelta(days=40), noon),
    }
    # Calendar days in the tenant timezone, as `start_of(...)` reads them: in
    # the hour after local midnight `now` is already Monday in London while
    # its UTC date is still Sunday.
    local_day = {k: get_display_locale().to_display_datetime(v).date() for k, v in stamps.items()}
    app.expected_week = sum(1 for d in local_day.values() if d >= week_start)
    app.expected_month = sum(1 for d in local_day.values() if d >= month_start)
    with psycopg.connect(app.db_url) as conn:
        for label, stamp in stamps.items():
            _insert(
                conn,
                "Mark",
                {"id": str(uuid.uuid4()), "label": label, "marked_at": stamp.isoformat()},
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


async def test_start_of_week_in_aggregate_where(app: _App) -> None:
    body = await _region(app, "hod_week", "since_monday")
    assert app.expected_week == 1, "seeds: only `now` is on/after Monday"
    assert str(app.expected_week) in _numbers(body), body[:600]


async def test_start_of_month_in_region_filter(app: _App) -> None:
    body = await _region(app, "hod_week", "this_month")
    assert app.expected_month in (1, 2)
    nums = _numbers(body)
    assert str(app.expected_month) in nums, body[:600]
    assert "4" not in nums, "the region filter must narrow the count"
