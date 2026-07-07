"""Uploader-gated pending-file route (#1551 Task 4).

``GET /_dazzle/documents/pending/{file_id}`` grants iff:
  - the file exists,
  - the caller is authenticated with the same id as ``metadata.uploaded_by``,
  - AND the file is not yet attached (``metadata.entity_id`` is empty/None).

All denials are opaque 404 (row-existence opacity).
"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.document_routes import create_document_routes


class _Store:
    def __init__(self, meta):  # type: ignore[no-untyped-def]
        self._m = meta

    def get_metadata(self, fid):  # type: ignore[no-untyped-def]
        return self._m if str(fid) == self._m.id else None


async def _agen(b: bytes):  # type: ignore[no-untyped-def]
    yield b


def _client(meta, *, authed_uid):  # type: ignore[no-untyped-def]
    async def auth_dep():  # type: ignore[no-untyped-def]
        return (
            SimpleNamespace(
                is_authenticated=bool(authed_uid),
                user=SimpleNamespace(id=authed_uid),
            )
            if authed_uid
            else None
        )

    # read_range must be async so serve_bytes can await it
    async def read_range(fid, s, e):  # type: ignore[no-untyped-def]
        return (_agen(b"%PDF-1.4"), meta)

    fs = SimpleNamespace(
        get_metadata=_Store(meta).get_metadata,
        read_range=read_range,
        download=None,
    )
    app = FastAPI()
    app.include_router(
        create_document_routes(
            file_service=fs,
            services={},
            cedar_access_specs={},
            fk_graph=None,
            optional_auth_dep=auth_dep,
            admin_personas=[],
            require_auth_by_default=True,
        )
    )
    return TestClient(app)


def _pending_meta(uid):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        size=8,
        content_type="application/pdf",
        filename="d.pdf",
        storage_backend="local",
        uploaded_by=uid,
        entity_name=None,
        entity_id=None,
        field_name=None,
    )


def test_uploader_gets_pending_file() -> None:
    meta = _pending_meta("owner")
    r = _client(meta, authed_uid="owner").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 200


def test_non_uploader_denied_404() -> None:
    meta = _pending_meta("owner")
    r = _client(meta, authed_uid="intruder").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 404


def test_attached_file_not_servable_via_pending() -> None:
    meta = _pending_meta("owner")
    meta.entity_id = "r1"  # already attached
    r = _client(meta, authed_uid="owner").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 404


def test_unauthenticated_denied_404() -> None:
    """No auth context → opaque 404 (uid is empty string)."""
    meta = _pending_meta("owner")
    r = _client(meta, authed_uid=None).get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 404


def test_unknown_file_id_404() -> None:
    """Unknown file_id (get_metadata returns None) → opaque 404."""
    meta = _pending_meta("owner")
    unknown_id = "22222222-2222-2222-2222-222222222222"
    r = _client(meta, authed_uid="owner").get(f"/_dazzle/documents/pending/{unknown_id}")
    assert r.status_code == 404
