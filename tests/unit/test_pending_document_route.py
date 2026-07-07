"""Uploader-gated pending-file route (#1551 Task 4).

``GET /_dazzle/documents/pending/{file_id}`` grants iff:
  - the file exists,
  - the caller is authenticated with the same id as ``metadata.uploaded_by``,
  - AND the file is not yet attached (``metadata.entity_id`` is empty/None).

All denials are opaque 404 (row-existence opacity).
"""

from datetime import UTC, datetime, timedelta
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


def _pending_meta(uid, *, created_at=None):  # type: ignore[no-untyped-def]
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
        created_at=created_at if created_at is not None else datetime.now(UTC),
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


# --- #1555: pending uploads are time-boxed (upload TTL) ---


def test_fresh_pending_file_within_ttl_served() -> None:
    """A pending file inside the TTL window is served normally."""
    meta = _pending_meta("owner", created_at=datetime.now(UTC) - timedelta(minutes=5))
    r = _client(meta, authed_uid="owner").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 200


def test_expired_pending_file_404() -> None:
    """#1555: a pending file older than the default 60-min TTL → opaque 404."""
    meta = _pending_meta("owner", created_at=datetime.now(UTC) - timedelta(hours=2))
    r = _client(meta, authed_uid="owner").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 404


def test_pending_ttl_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DAZZLE_PENDING_UPLOAD_TTL_MINUTES tunes the window; <=0 disables it."""
    # 0 disables the time-box: a 2h-old file is still served.
    monkeypatch.setenv("DAZZLE_PENDING_UPLOAD_TTL_MINUTES", "0")
    old = _pending_meta("owner", created_at=datetime.now(UTC) - timedelta(hours=2))
    r = _client(old, authed_uid="owner").get(f"/_dazzle/documents/pending/{old.id}")
    assert r.status_code == 200

    # A tight 1-min window 404s a 5-min-old file.
    monkeypatch.setenv("DAZZLE_PENDING_UPLOAD_TTL_MINUTES", "1")
    recent = _pending_meta("owner", created_at=datetime.now(UTC) - timedelta(minutes=5))
    r2 = _client(recent, authed_uid="owner").get(f"/_dazzle/documents/pending/{recent.id}")
    assert r2.status_code == 404
