"""File leftover ?entity= must not invent a persist (cycle 2250).

leftover-honest search entity already exists (oral #117 /
leftover_honest_search_entity). POST ``/files/upload`` still stored
leftover ``zzz`` / ``ghost`` / ``MysteryEntity`` as ``entity_name``
and invented a file-metadata persist. The same leftover on GET
``/files/entity/{entity}/...`` invented an empty list. Valid
declared entity names ride; leftover stays put (400, no write).
Absent / blank still first-visit (unassociated). Live
project_tracker ``entity Attachment`` ``file: file``. Oral #120 —
not leftover search ``?entity=`` fleet-restrict (oral #117), not
leftover catalog picker (oral #69).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.file_routes import (
    create_file_routes,
    leftover_honest_file_entity,
)

_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "file_routes.py"
)
_SERVER = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "server.py"
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "project_tracker" / "dsl" / "app.dsl"


@pytest.mark.parametrize(
    ("raw", "declared", "expected"),
    [
        ("Attachment", ("Attachment", "Task"), "Attachment"),
        ("Task", ("Attachment", "Task"), "Task"),
        ("  Attachment  ", ("Attachment", "Task"), "Attachment"),
        ("", ("Attachment", "Task"), ""),
        (None, ("Attachment", "Task"), ""),
        ("   ", ("Attachment", "Task"), ""),
        ("zzz", ("Attachment", "Task"), None),
        ("ghost", ("Attachment", "Task"), None),
        ("MysteryEntity", ("Attachment", "Task"), None),
        ("attachment", ("Attachment", "Task"), None),
        ("Document", ("Attachment", "Task"), None),
        (["Attachment"], ("Attachment", "Task"), None),
        ({"entity": "Attachment"}, ("Attachment", "Task"), None),
        (1, ("Attachment", "Task"), None),
        (True, ("Attachment", "Task"), None),
        ("zzz", None, "zzz"),
        ("Attachment", None, "Attachment"),
        (["Attachment"], None, None),
    ],
    ids=[
        "attachment-rides",
        "task-rides",
        "strip",
        "empty-first-visit",
        "none-first-visit",
        "blank-first-visit",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-mystery",
        "leftover-case",
        "leftover-other-entity",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
        "no-catalog-rides-zzz",
        "no-catalog-rides-name",
        "no-catalog-leftover-list",
    ],
)
def test_leftover_honest_file_entity_does_not_invent(
    raw: object, declared: object, expected: str | None
) -> None:
    assert leftover_honest_file_entity(raw, declared) == expected


def _mount(
    *, declared: tuple[str, ...] | None = ("Attachment", "Task")
) -> tuple[TestClient, MagicMock]:
    app = FastAPI()
    file_service = MagicMock()
    metadata = MagicMock()
    metadata.id = "file-001"
    metadata.filename = "brief.pdf"
    metadata.content_type = "application/pdf"
    metadata.size = 100
    metadata.url = "/files/file-001"
    metadata.created_at = MagicMock(isoformat=lambda: "2026-01-01T00:00:00")
    file_service.upload = AsyncMock(return_value=metadata)
    file_service.get_entity_files = MagicMock(return_value=[])
    create_file_routes(app, file_service, declared_entities=declared)
    return TestClient(app), file_service


def test_leftover_entity_zzz_does_not_invent_persist() -> None:
    client, svc = _mount()
    resp = client.post(
        "/files/upload?entity=zzz",
        files={"file": ("brief.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid entity"}
    svc.upload.assert_not_called()


def test_leftover_entity_ghost_does_not_invent_persist() -> None:
    client, svc = _mount()
    resp = client.post(
        "/files/upload?entity=ghost",
        files={"file": ("brief.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid entity"
    svc.upload.assert_not_called()


def test_leftover_entity_mystery_does_not_invent_persist() -> None:
    client, svc = _mount()
    resp = client.post(
        "/files/upload?entity=MysteryEntity",
        files={"file": ("brief.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 400
    svc.upload.assert_not_called()


def test_valid_entity_still_uploads() -> None:
    client, svc = _mount()
    resp = client.post(
        "/files/upload?entity=Attachment&entity_id=a1&field=file",
        files={"file": ("brief.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 200
    svc.upload.assert_called_once()
    assert svc.upload.call_args.kwargs["entity_name"] == "Attachment"


def test_absent_entity_still_first_visit_unassociated() -> None:
    client, svc = _mount()
    resp = client.post(
        "/files/upload",
        files={"file": ("brief.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 200
    svc.upload.assert_called_once()
    assert svc.upload.call_args.kwargs["entity_name"] is None


def test_leftover_entity_list_does_not_invent_empty() -> None:
    client, svc = _mount()
    resp = client.get("/files/entity/zzz/a1")
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid entity"}
    svc.get_entity_files.assert_not_called()


def test_valid_entity_list_still_lists() -> None:
    client, svc = _mount()
    resp = client.get("/files/entity/Attachment/a1")
    assert resp.status_code == 200
    svc.get_entity_files.assert_called_once_with("Attachment", "a1", None)


def test_helper_source_pins_file_entity_leftover() -> None:
    routes = _ROUTES.read_text()
    assert "def leftover_honest_file_entity" in routes
    assert "leftover_honest_auth_error" in routes
    assert 'return JSONResponse(content={"error": "invalid entity"}, status_code=400)' in routes
    assert "Response(\n            status_code=400,\n            content=" not in routes
    assert "declared_entities=_declared_entities" in _SERVER.read_text()


def test_live_project_tracker_attachment_file() -> None:
    dsl = _LIVE.read_text()
    assert 'entity Attachment "Attachment":' in dsl
    assert "file: file required" in dsl
