"""Real-Postgres proof that an edit form can clear an optional field (#1848).

cyfuture's repro: ``Contact.initials`` holds "XQ", the edit form is saved with
Initials emptied, the browser sends ``PUT /contacts/<id>`` with ``initials=``
(form-urlencoded), the response is 200 and the column still says "XQ". The
service and the repository both dropped every ``None`` from the update.

This boots a small DSL in ``tmp_path`` against a disposable database and drives
the generated update endpoint the way the edit form does: every rendered field
posted, the cleared one empty. An optional str, ref and date each go
value → empty → NULL; a field not sent is left alone; a required field sent
empty is a 422 and changes nothing.

The project lives in ``tmp_path``, so no ``xdist_group`` pin is needed.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_BASE_URL = "http://clear-probe.local"

_MANIFEST = """[project]
name = "clear_probe"
version = "0.1.0"
root = "clear_probe"

[modules]
paths = ["./dsl"]
"""

_DSL = """module clear_probe
app clear_probe "Clear Probe"

entity Agent "Agent":
  id: uuid pk
  name: str(100) required

entity Contact "Contact":
  id: uuid pk
  name: str(200) required
  initials: str(3)
  agent: ref Agent
  follow_up: date
  notes: text

surface agent_list "Agents":
  uses entity Agent
  mode: list
  section main:
    field name "Name"

surface agent_create "New Agent":
  uses entity Agent
  mode: create
  section main:
    field name "Name"

surface contact_create "New Contact":
  uses entity Contact
  mode: create
  section main:
    field name "Name"
    field initials "Initials"
    field agent "Agent"
    field follow_up "Follow up"
    field notes "Notes"

surface contact_view "Contact":
  uses entity Contact
  mode: view
  section main:
    field name "Name"
    field notes "Notes"

surface contact_list "Contacts":
  uses entity Contact
  mode: list
  section main:
    field name "Name"

surface contact_edit "Edit Contact":
  uses entity Contact
  mode: edit
  section main:
    field name "Name"
    field initials "Initials"
    field agent "Agent"
    field follow_up "Follow up"
"""

_FORM = {"content-type": "application/x-www-form-urlencoded"}


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[Any]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase
    from dazzle.testing.http_policies import csrf_headers, prime_csrf_cookie

    root = tmp_path / "clear_probe"
    (root / "dsl").mkdir(parents=True)
    (root / "dazzle.toml").write_text(_MANIFEST)
    (root / "dsl" / "app.dsl").write_text(_DSL)

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(root, db_url)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=built.app), base_url=_BASE_URL
            ) as c:
                await prime_csrf_cookie(c, _BASE_URL)
                c.headers.update(csrf_headers(c))
                yield c
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


async def _seed(client: Any) -> tuple[str, dict[str, str]]:
    resp = await client.post("/agents", json={"name": "Ada"})
    assert resp.status_code in (200, 201), resp.text[:400]
    values = {
        "name": "Quentin",
        "initials": "XQ",
        "agent": resp.json()["id"],
        "follow_up": "2026-11-01",
    }
    resp = await client.post("/contacts", json={**values, "notes": "keep me"})
    assert resp.status_code in (200, 201), resp.text[:400]
    return resp.json()["id"], values


def _stored(row: dict[str, Any], field: str) -> Any:
    value = row[field]
    return value["id"] if isinstance(value, dict) else value  # an included ref


@pytest.mark.parametrize("field", ["initials", "agent", "follow_up"])
async def test_edit_form_clears_an_optional_field(client: Any, field: str) -> None:
    contact_id, values = await _seed(client)

    # The edit form posts every rendered field; the cleared one is empty.
    resp = await client.put(f"/contacts/{contact_id}", data={**values, field: ""}, headers=_FORM)
    assert resp.status_code == 200, resp.text[:400]

    row = (await client.get(f"/contacts/{contact_id}")).json()
    assert row[field] is None
    for other in set(values) - {field}:
        assert _stored(row, other) == values[other]
    assert row["notes"] == "keep me"  # not on the form, not posted, not touched


async def test_json_null_clears_and_omitted_fields_are_untouched(client: Any) -> None:
    contact_id, values = await _seed(client)

    resp = await client.put(f"/contacts/{contact_id}", json={"notes": None})
    assert resp.status_code == 200, resp.text[:400]

    row = (await client.get(f"/contacts/{contact_id}")).json()
    assert row["notes"] is None
    assert {k: _stored(row, k) for k in values} == values


async def test_required_field_sent_empty_is_rejected(client: Any) -> None:
    contact_id, values = await _seed(client)

    resp = await client.put(f"/contacts/{contact_id}", data={**values, "name": ""}, headers=_FORM)
    assert resp.status_code == 422, resp.text[:400]

    row = (await client.get(f"/contacts/{contact_id}")).json()
    assert row["name"] == "Quentin"
