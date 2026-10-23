"""Real-Postgres proof that workspace region chips carry a person's declared
initials and photo (#1849).

Regions load to-one refs through the FK-display JOIN path (#865), which used to
fold only ``{rel}__display`` into the ref dict — so the chip derived initials
from the name and never showed a photo. The JOIN now also projects the target's
declared ``initials`` / ``avatar_url``; this boots a copy of
``fixtures/scope_runtime`` with a ``Contact`` + ``Notification`` pair appended
and reads the region as the admin. The copy lives in ``tmp_path``, so no
``xdist_group`` pin is needed.
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
_PASSWORD = "person-chip-password"  # nosec B105 — disposable scratch DB only
_ADMIN = "admin@scope.test"
_PHOTO = "https://img.example.test/ada.png"

_CHIP_DSL = """

entity Contact "Contact":
  display_field: name
  id: uuid pk
  name: str(120) required
  initials: str(4)
  avatar_url: url

  permit:
    read: role(admin)
    list: role(admin)

  scope:
    read: all
      as: admin
    list: all
      as: admin


entity Notification "Notification":
  id: uuid pk
  title: str(200) required
  recipient: ref Contact required

  permit:
    read: role(admin)
    list: role(admin)

  scope:
    read: all
      as: admin
    list: all
      as: admin


workspace inbox_desk "Inbox Desk":
  purpose: "See who each notification went to"
  access: persona(admin)

  notifications:
    source: Notification
    display: list
    sort: title asc
    limit: 5
"""


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_person_chip"
    shutil.copytree(_FIXTURE, root)
    domain = root / "dsl" / "domain.dsl"
    domain.write_text(domain.read_text() + _CHIP_DSL)
    return root


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


def _seed(db_url: str, auth_store: Any) -> None:
    import psycopg

    if auth_store.get_user_by_email(_ADMIN) is None:
        auth_store.create_user(_ADMIN, _PASSWORD, roles=["admin"])
    with psycopg.connect(db_url) as conn:
        declared = str(uuid.uuid4())
        pictured = str(uuid.uuid4())
        _insert(conn, "Contact", {"id": declared, "name": "Demo Xero Sync", "initials": "XQ"})
        _insert(conn, "Contact", {"id": pictured, "name": "Ada Lovelace", "avatar_url": _PHOTO})
        _insert(
            conn, "Notification", {"id": str(uuid.uuid4()), "title": "A", "recipient": declared}
        )
        _insert(
            conn, "Notification", {"id": str(uuid.uuid4()), "title": "B", "recipient": pictured}
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
        _seed(db_url, auth_store)
        try:
            yield _App(_probe_transport(httpx.ASGITransport(app=built.app)))
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


async def test_region_chip_shows_declared_initials_and_photo(app: _App) -> None:
    import httpx

    from dazzle.cli.rbac import _login

    async with httpx.AsyncClient(
        transport=app.transport, base_url=_BASE_URL, follow_redirects=True
    ) as client:
        await _login(client, _BASE_URL, _ADMIN, _PASSWORD)
        resp = await client.get("/api/workspaces/inbox_desk/regions/notifications")
    assert resp.status_code == 200, resp.text[:400]
    body = resp.text

    assert "Demo Xero Sync" in body and "dz-avatar" in body
    assert ">XQ</span>" in body, "declared initials win over the name-derived XS"
    assert ">DX</span>" not in body and ">XS</span>" not in body
    assert f'<img src="{_PHOTO}"' in body, "the declared photo reaches the region chip"
