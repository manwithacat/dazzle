"""hx-pdf P1 — the scope-gated document range-proxy route (#162).

`GET /_dazzle/documents/{entity}/{entity_id}/{field}/file` streams a
file-field's bytes gated by the SAME access core the entity's read verb
uses (`gated_read` — document access IS entity access; denied/missing
collapse to an opaque 404). `/download` adds attachment disposition +
an audit event. Range requests are validated per the hx-pdf spec §18.

Unlike the legacy `/files/{id}` reads (ID-keyed, no entity scope —
follow-up issue filed by the P1 review), every response here requires:
entity resolves → record readable under scope → the stored field value
actually references the requested file → the file's metadata triple
(entity/id/field) matches the URL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.document_routes import create_document_routes

ENTITY_ID = uuid.uuid4()
FILE_ID = uuid.uuid4()
PDF_BYTES = b"%PDF-1.4 " + bytes(range(256)) * 4  # 1033 bytes, binary-ish


@dataclass
class _Meta:
    id: Any
    filename: str
    content_type: str
    size: int
    entity_name: str | None
    entity_id: str | None
    field_name: str | None
    created_at: datetime | None = None


class _FakeFileService:
    def __init__(self, meta: _Meta | None, content: bytes = PDF_BYTES) -> None:
        self._meta = meta
        self._content = content

    def get_metadata(self, file_id: Any) -> _Meta | None:
        if self._meta and str(file_id) == str(self._meta.id):
            return self._meta
        return None

    async def download(self, file_id: Any) -> tuple[bytes, _Meta]:
        if not self._meta or str(file_id) != str(self._meta.id):
            raise FileNotFoundError(file_id)
        return self._content, self._meta


class _FakeService:
    """Plain-read path (no cedar spec): execute('read', id=...) → record."""

    def __init__(self, record: dict[str, Any] | None) -> None:
        self._record = record
        self.calls: list[dict[str, Any]] = []

    async def execute(self, *, operation: str, id: Any, **kw: Any) -> Any:
        self.calls.append({"operation": operation, "id": id, **kw})
        if self._record and str(id) == str(self._record.get("id")):
            return self._record
        return None


class _FakeAudit:
    """Mirrors AuditLogger.log_decision's REAL signature — the route must
    call the real API (the P1 review caught a phantom log_event call the
    old blanket-except swallowed: the assert-on-mock counter-prior)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def log_decision(
        self,
        operation: str = "",
        entity_name: str = "",
        entity_id: str | None = None,
        decision: str = "",
        matched_policy: str = "",
        policy_effect: str = "",
        user_id: str | None = None,
        user_email: str | None = None,
        user_roles: list[str] | None = None,
        ip_address: str | None = None,
        request_path: str | None = None,
        request_method: str | None = None,
        tenant_id: str | None = None,
        evaluation_time_us: int | None = None,
        field_changes: str | None = None,
    ) -> None:
        self.events.append(
            {
                "operation": operation,
                "entity_name": entity_name,
                "entity_id": entity_id,
                "decision": decision,
                "matched_policy": matched_policy,
            }
        )


def _meta(**over: Any) -> _Meta:
    base: dict[str, Any] = {
        "id": FILE_ID,
        "filename": "contract.pdf",
        "content_type": "application/pdf",
        "size": len(PDF_BYTES),
        "entity_name": "Attachment",
        "entity_id": str(ENTITY_ID),
        "field_name": "file",
    }
    base.update(over)
    return _Meta(**base)


def _client(
    *,
    record: dict[str, Any] | None = "DEFAULT",  # type: ignore[assignment]
    meta: _Meta | None = "DEFAULT",  # type: ignore[assignment]
    audit: Any = None,
    specs: dict[str, Any] | None = None,
    auth_dep: Any = None,
    require_auth_by_default: bool = False,
) -> TestClient:
    if record == "DEFAULT":
        record = {"id": str(ENTITY_ID), "file": f"/files/{FILE_ID}/download"}
    if meta == "DEFAULT":
        meta = _meta()
    app = FastAPI()
    router = create_document_routes(
        file_service=_FakeFileService(meta),
        services={"Attachment": _FakeService(record)},
        cedar_access_specs=specs or {},
        fk_graph=None,
        optional_auth_dep=auth_dep,
        admin_personas=None,
        audit_logger=audit,
        require_auth_by_default=require_auth_by_default,
    )
    app.include_router(router)
    return TestClient(app)


def _url(entity: str = "Attachment", eid: Any = None, field: str = "file") -> str:
    return f"/_dazzle/documents/{entity}/{eid or ENTITY_ID}/{field}/file"


# ── resolution + opacity ────────────────────────────────────────────


def test_unknown_entity_is_opaque_404() -> None:
    r = _client().get(_url(entity="Nope"))
    assert r.status_code == 404


def test_missing_record_is_opaque_404() -> None:
    r = _client(record=None).get(_url())
    assert r.status_code == 404


def test_invalid_entity_id_is_404() -> None:
    r = _client().get(_url(eid="not-a-uuid"))
    assert r.status_code == 404


def test_empty_field_value_is_404() -> None:
    r = _client(record={"id": str(ENTITY_ID), "file": ""}).get(_url())
    assert r.status_code == 404


def test_metadata_triple_mismatch_is_opaque_404() -> None:
    # the file exists but belongs to a DIFFERENT entity — holding a valid
    # record + a foreign file URL must not leak the bytes
    r = _client(meta=_meta(entity_name="Invoice")).get(_url())
    assert r.status_code == 404


def test_field_name_mismatch_is_404() -> None:
    r = _client(meta=_meta(field_name="avatar")).get(_url())
    assert r.status_code == 404


# ── streaming + headers ─────────────────────────────────────────────


def test_full_read_200_with_security_headers() -> None:
    r = _client().get(_url())
    assert r.status_code == 200
    assert r.content == PDF_BYTES
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["accept-ranges"] == "bytes"
    assert "private" in r.headers["cache-control"]
    assert r.headers["content-type"].startswith("application/pdf")
    assert 'inline; filename="contract.pdf"' in r.headers["content-disposition"]


def test_filename_is_sanitized_in_disposition() -> None:
    evil = _meta(filename='a"b\r\nSet-Cookie: x=y.pdf')
    r = _client(meta=evil).get(_url())
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert "\r" not in cd and "\n" not in cd  # header injection stripped
    # the quoted filename= value carries no raw quote characters
    quoted = cd.split('filename="', 1)[1].split('"', 1)[0]
    assert '"' not in quoted
    # the RFC 6266 filename* form is percent-encoded (no raw specials)
    star = cd.split("filename*=UTF-8''", 1)[1]
    assert '"' not in star and ";" not in star and " " not in star


def test_bare_uuid_field_value_accepted() -> None:
    r = _client(record={"id": str(ENTITY_ID), "file": str(FILE_ID)}).get(_url())
    assert r.status_code == 200


# ── Range validation (spec §18) ─────────────────────────────────────


def test_range_206_with_content_range() -> None:
    r = _client().get(_url(), headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.content == PDF_BYTES[:100]
    assert r.headers["content-range"] == f"bytes 0-99/{len(PDF_BYTES)}"
    assert r.headers["content-length"] == "100"


def test_open_ended_range() -> None:
    r = _client().get(_url(), headers={"Range": "bytes=1000-"})
    assert r.status_code == 206
    assert r.content == PDF_BYTES[1000:]


def test_suffix_range() -> None:
    r = _client().get(_url(), headers={"Range": "bytes=-33"})
    assert r.status_code == 206
    assert r.content == PDF_BYTES[-33:]


def test_unsatisfiable_range_416() -> None:
    r = _client().get(_url(), headers={"Range": f"bytes={len(PDF_BYTES)}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(PDF_BYTES)}"


def test_malformed_range_served_whole_200() -> None:
    # RFC 9110: a syntactically invalid Range header is ignored
    r = _client().get(_url(), headers={"Range": "bytes=zz-yy"})
    assert r.status_code == 200
    assert r.content == PDF_BYTES


def test_multi_range_served_whole_200() -> None:
    # multipart/byteranges is out of v1 scope — serve the full body
    r = _client().get(_url(), headers={"Range": "bytes=0-1,5-9"})
    assert r.status_code == 200


# ── download variant ────────────────────────────────────────────────


def test_download_sets_attachment_and_audits() -> None:
    audit = _FakeAudit()
    r = _client(audit=audit).get(_url()[: -len("/file")] + "/download")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment;")
    assert len(audit.events) == 1
    ev = audit.events[0]
    assert ev.get("entity_name") == "Attachment"
    assert ev.get("operation") == "document_download"
    assert ev.get("decision") == "allow"


# ── auth wiring (the P1 review's SEV-1 region) ──────────────────────


@dataclass
class _AuthCtx:
    is_authenticated: bool
    user: Any = None


def test_no_spec_entity_denies_anonymous_when_app_enforces_auth() -> None:
    """The REST read posture applies: an authenticated app's no-spec
    entity must not serve bytes to anonymous callers (opaque 404) —
    the review's anonymous-bypass finding."""

    async def anon_dep() -> Any:
        return _AuthCtx(is_authenticated=False)

    r = _client(auth_dep=anon_dep, require_auth_by_default=True).get(_url())
    assert r.status_code == 404


def test_no_spec_entity_serves_authenticated_caller() -> None:
    async def user_dep() -> Any:
        return _AuthCtx(is_authenticated=True)

    r = _client(auth_dep=user_dep, require_auth_by_default=True).get(_url())
    assert r.status_code == 200


def test_cedar_path_receives_the_dependency_auth_context(monkeypatch) -> None:
    """The auth context must flow from the FastAPI dependency into
    gated_read's AccessContext (the review found request.state was read
    instead — never populated → 500 on every gated entity)."""
    from dazzle.http.runtime import document_routes as dr

    marker = _AuthCtx(is_authenticated=True, user=object())
    seen: dict[str, Any] = {}

    async def fake_gated_read(service: Any, access: Any, eid: Any, **kw: Any) -> Any:
        seen["auth"] = access.auth_context
        return {"id": str(ENTITY_ID), "file": f"/files/{FILE_ID}/download"}

    monkeypatch.setattr(dr, "gated_read", fake_gated_read)

    async def user_dep() -> Any:
        return marker

    r = _client(specs={"Attachment": object()}, auth_dep=user_dep).get(_url())
    assert r.status_code == 200
    assert seen["auth"] is marker


def test_cedar_denial_is_opaque_404(monkeypatch) -> None:
    from dazzle.http.runtime import document_routes as dr
    from dazzle.http.runtime.access.gated import RecordNotFound

    async def deny(service: Any, access: Any, eid: Any, **kw: Any) -> Any:
        raise RecordNotFound("Attachment")

    monkeypatch.setattr(dr, "gated_read", deny)

    async def user_dep() -> Any:
        return _AuthCtx(is_authenticated=True)

    r = _client(specs={"Attachment": object()}, auth_dep=user_dep).get(_url())
    assert r.status_code == 404


# ── disposition hardening ───────────────────────────────────────────


def test_non_ascii_filename_survives_via_rfc6266() -> None:
    r = _client(meta=_meta(filename="契約書.pdf")).get(_url())
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert "filename*=UTF-8''" in cd  # original rides the RFC 6266 form


def test_unsafe_content_type_downgrades_inline_to_attachment() -> None:
    r = _client(meta=_meta(content_type="text/html")).get(_url())
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment;")


def test_single_byte_range() -> None:
    r = _client().get(_url(), headers={"Range": "bytes=0-0"})
    assert r.status_code == 206
    assert r.content == PDF_BYTES[:1]
