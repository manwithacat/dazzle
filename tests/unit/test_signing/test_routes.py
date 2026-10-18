"""Auto-mounted signing routes (#1283 phase 3d) through FastAPI ``TestClient``.

A hand-rolled async repository stands in for the DB; the contract under test
is the route layer's use of ``read`` / ``update``. Every refusal (bad, foreign,
expired or tampered token; wrong credential; terminal state) is its own table
row with an id naming what it protects, and every refusal also asserts that
the row was not written.

The router factory's None-vs-router choice is pinned by
``test_integration.py::TestRouterFromAppSpec`` against linked DSL.
"""

from __future__ import annotations

import base64
import io
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from dazzle.core.ir import EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.signing.cert import generate_cert_chain_b64
from dazzle.signing.tokens import SigningError, mint_token, token_hash

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

from dazzle.http.runtime.tenant.resolver import ResolvedTenant  # noqa: E402
from dazzle.http.runtime.tenant_isolation import (  # noqa: E402
    get_current_tenant_id,
    set_current_tenant_id,
)
from dazzle.signing.routes import (  # noqa: E402
    _active_signing_states,
    _signing_rls_tenant,
    create_signing_routes,
)

PRESENT = object()  # expected patch value meaning "is set"
EMAIL = "a@example.com"
_MOD = "tests.unit.test_signing.test_routes"

# ---------------------------------------------------------------------
# Fakes and project callables (resolved by dotted path, like real hooks)
# ---------------------------------------------------------------------


class _MockRepo:
    """Minimal async repository covering ``read`` + ``update``."""

    def __init__(self, rows: dict[str, Any]) -> None:
        self.rows = rows
        self.update_calls: list[tuple[str, dict[str, Any]]] = []
        self.tenant_ids_at_read: list[str | None] = []

    async def read(self, record_id: Any) -> Any:
        self.tenant_ids_at_read.append(get_current_tenant_id())
        return self.rows.get(str(record_id))

    async def update(self, record_id: Any, data: dict[str, Any]) -> Any:
        self.update_calls.append((str(record_id), data))
        row = self.rows[str(record_id)]
        row.update(data)
        return row


class _MockFileService:
    """Records uploads and returns a fake URL; optionally serves one stored PDF."""

    def __init__(self, *, fail_upload: bool = False, record_id: str = "") -> None:
        self.uploads: list[dict[str, Any]] = []
        self.fail_upload = fail_upload
        self.storage: Any = None
        self.metadata_store: Any = None
        self.file_id = uuid4()
        self.record_id = record_id
        self.data = b"%PDF-1.7 signed-copy-bytes"

    async def upload(self, file: Any, filename: str, **kw: Any) -> Any:
        if self.fail_upload:
            raise RuntimeError("simulated FileService.upload failure (TR-49)")
        self.uploads.append({"filename": filename, "size": len(file.read()), **kw})
        return SimpleNamespace(url=f"/files/{filename}")

    def get_metadata(self, file_id: Any) -> Any:
        if not self.record_id or str(file_id) != str(self.file_id):
            return None
        return SimpleNamespace(
            id=self.file_id,
            size=len(self.data),
            content_type="application/pdf",
            filename="signed-copy.pdf",
            entity_name="Contract",
            entity_id=self.record_id,
        )

    async def read_range(self, file_id: Any, start: int, end: int) -> Any:
        # The signed-copy route streams through this (#1551 serve_bytes contract).
        chunk = self.data[start : end + 1]

        async def _aiter() -> Any:
            yield chunk

        return _aiter(), len(chunk)


def reject_validator(*, entity: Any, row: Any) -> None:
    raise SigningError("validator says no")


def custom_template(*, entity: Any, row: Any) -> str:
    return "<h1>CUSTOM TEMPLATE BODY MARKER</h1>"


def non_str_template(*, entity: Any, row: Any) -> None:
    return None


_resend_calls: list[dict[str, Any]] = []


def record_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    _resend_calls.append({"email": email, "signing_url": signing_url})


async def async_record_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    """Must be awaited on the running loop, never run_until_complete'd."""
    _resend_calls.append({"email": email, "signing_url": signing_url})


def failing_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    raise SigningError("mail server down")


def bare_raise_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    raise ValueError(f"boom with {signing_url}")  # must not leak signing_url


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "test-secret-not-for-prod")
    _resend_calls.clear()


@pytest.fixture
def signing_cert_env(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fpdf")
    pytest.importorskip("pyhanko")
    b64, password = generate_cert_chain_b64("Test Org")
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", b64)
    monkeypatch.setenv("SIGNING_CERT_PASSWORD", password)
    from dazzle.signing.service import _get_signer

    _get_signer.cache_clear()


def _entity(**updates: Any) -> EntitySpec:
    pk = FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID), modifiers=[FieldModifier.PK])
    return EntitySpec(name="Contract", title="Contract", fields=[pk], signable=True, **updates)


def _app(
    rows: dict[str, Any],
    *,
    entity: dict[str, Any] | None = None,
    middleware: type | None = None,
    **route_kw: Any,
) -> tuple[TestClient, _MockRepo]:
    repo = _MockRepo(rows)
    router = create_signing_routes(
        [_entity(**(entity or {}))], repositories={"Contract": repo}, **route_kw
    )
    assert router is not None
    app = FastAPI()
    if middleware is not None:
        app.add_middleware(middleware)
    app.include_router(router)
    return TestClient(app), repo


def _token(kind: str, record_id: str) -> str | None:
    return {
        "valid": mint_token(record_id, EMAIL),
        "missing": None,
        "garbage": "not-a-real-token",
        "other-record": mint_token(str(uuid4()), EMAIL),
        "other-email": mint_token(record_id, "attacker@example.com"),
        # Negative expiry → already expired but HMAC-valid (recovery path).
        "expired": mint_token(record_id, EMAIL, expires_hours=-1),
    }[kind]


def _assert_patch(repo: _MockRepo, expected: dict[str, Any] | None) -> None:
    if expected is None:
        assert repo.update_calls == []
        return
    [(_, patch)] = repo.update_calls
    for key, want in expected.items():
        assert patch[key] is not None if want is PRESENT else patch[key] == want, key


# ---------------------------------------------------------------------
# GET /sign/{entity}/{id}
# ---------------------------------------------------------------------

GET_CASES = [
    # (row status or None, route kwargs, token, status, must contain, must not contain, patch)
    pytest.param(
        "sent", {}, "missing", 400, ["Missing signing token"], [], None, id="missing-token-400"
    ),
    pytest.param("sent", {}, "garbage", 403, [], [], None, id="invalid-token-403"),
    pytest.param("sent", {}, "other-record", 403, [], [], None, id="token-for-other-record-403"),
    pytest.param(None, {}, "valid", 404, [], [], None, id="unknown-record-404"),
    pytest.param(
        "sent",
        {"resend_hook": f"{_MOD}.record_resend"},
        "garbage",
        403,
        [],
        ["Request a new signing link"],
        None,
        id="tampered-token-gets-no-recovery-offer-TR-53",
    ),
    pytest.param(
        "sent",
        {"resend_hook": f"{_MOD}.record_resend"},
        "expired",
        403,
        ["expired", "/resend", "Request a new signing link"],
        [],
        None,
        id="expired-token-with-hook-offers-resend-TR-53",
    ),
    pytest.param(
        "sent",
        {"support_contact": "help@acme.example"},
        "expired",
        403,
        ["expired", "help@acme.example"],
        ["/resend"],
        None,
        id="expired-token-without-hook-shows-support-contact-TR-53",
    ),
    pytest.param(
        "signed",
        {},
        "valid",
        200,
        ["already been signed"],
        ["signed-copy"],
        None,
        id="terminal-status-short-circuits-without-write",
    ),
    pytest.param(
        "sent",
        {},
        "valid",
        200,
        [
            'data-island="signing_pad"',
            "/static/js/islands/signing-pad.js",
            'class="signing-document"',
        ],
        [],
        {"status": "viewed", "viewed_at": PRESENT, "signer_user_agent": PRESENT},
        id="sent-transitions-to-viewed-and-mounts-pad",
    ),
    pytest.param(
        "viewed",
        {},
        "valid",
        200,
        ['data-island="signing_pad"', "This is a placeholder document body"],
        ["<script>"],
        None,
        id="viewed-no-redundant-write-stub-body-token-escaped",
    ),
]


@pytest.mark.parametrize(
    ("status", "route_kw", "token", "code", "contains", "absent", "patch"), GET_CASES
)
def test_get_signing_page(
    status: str | None,
    route_kw: dict[str, Any],
    token: str,
    code: int,
    contains: list[str],
    absent: list[str],
    patch: dict[str, Any] | None,
) -> None:
    record_id = str(uuid4())
    client, repo = _app({record_id: {"status": status}} if status else {}, **route_kw)
    tok = _token(token, record_id)
    resp = client.get(f"/sign/Contract/{record_id}", params={"token": tok} if tok else {})
    assert resp.status_code == code, resp.text
    for fragment in contains:
        assert fragment in resp.text, fragment
    for fragment in absent:
        assert fragment not in resp.text, fragment
    _assert_patch(repo, patch)


def test_get_page_shows_intended_signatory_email() -> None:
    """TR-15: bearer links cannot hard-gate identity, so the page names the
    token's bound signatory to make a mis-delivered link visible."""
    record_id = str(uuid4())
    client, _ = _app({record_id: {"status": "sent"}})
    token = mint_token(record_id, "devon.park@retailco.example")
    resp = client.get(f"/sign/Contract/{record_id}", params={"token": token})
    assert resp.status_code == 200
    assert 'class="signing-intended-for"' in resp.text
    assert "intended for" in resp.text.lower()
    assert "devon.park@retailco.example" in resp.text


@pytest.mark.parametrize(
    ("entity", "template_file", "expected"),
    [
        pytest.param(
            {"signing_template": f"{_MOD}.custom_template"},
            None,
            ["CUSTOM TEMPLATE BODY MARKER"],
            id="project-callable-wins-#1287",
        ),
        pytest.param(
            {},
            "<p>Party: {{ row.party }}</p><p>Scope: {{ row.scope }}</p>",
            ["<p>Party: Acme Corp</p>", "<p>Scope: Annual audit</p>"],
            id="templates-letters-file-rendered-#1287",
        ),
        pytest.param(
            {},
            "",
            ["This is a placeholder document body"],
            id="no-template-file-falls-back-to-stub",
        ),
    ],
)
def test_get_page_embeds_document_body(
    entity: dict[str, Any], template_file: str | None, expected: list[str], tmp_path: Any
) -> None:
    if template_file:
        letters = tmp_path / "templates" / "letters" / "Contract"
        letters.mkdir(parents=True)
        (letters / "default.html.j2").write_text(template_file)
    record_id = str(uuid4())
    row = SimpleNamespace(id=record_id, status="viewed", party="Acme Corp", scope="Annual audit")
    client, _ = _app({record_id: row}, entity=entity, project_root=tmp_path)
    resp = client.get(f"/sign/Contract/{record_id}", params={"token": _token("valid", record_id)})
    assert resp.status_code == 200
    assert 'class="signing-document"' in resp.text
    for fragment in expected:
        assert fragment in resp.text, fragment


# ---------------------------------------------------------------------
# POST /api/sign/{entity}/{id}
# ---------------------------------------------------------------------

POST_CASES = [
    # (row status, entity overrides, path entity, token, body, status, contains, patch)
    pytest.param("viewed", {}, "Contract", "garbage", {}, 403, None, None, id="invalid-token-403"),
    pytest.param(
        "viewed",
        {},
        "Contract",
        "other-record",
        {},
        403,
        None,
        None,
        id="token-for-other-record-403",
    ),
    pytest.param("signed", {}, "Contract", "valid", {}, 409, None, None, id="terminal-status-409"),
    pytest.param("viewed", {}, "Otherwise", "valid", {}, 404, None, None, id="unknown-entity-404"),
    pytest.param(
        "viewed",
        {"signing_validator": f"{_MOD}.reject_validator"},
        "Contract",
        "valid",
        {},
        400,
        "validator says no",
        None,
        id="validator-signing-error-blocks-sign",
    ),
    pytest.param(
        "viewed",
        {"signing_validator": "UPPERCASE.NotAllowed.fn"},
        "Contract",
        "valid",
        {},
        400,
        "is not a valid dotted path",
        None,
        id="validator-path-outside-dotted-shape-refused",
    ),
    pytest.param(
        "viewed",
        {},
        "Contract",
        "valid",
        {"decline": True, "decline_reason": "no"},
        200,
        '{"status":"declined"}',
        {"status": "declined", "signing_token_hash": PRESENT},
        id="decline-transitions-to-declined",
    ),
]


@pytest.mark.parametrize(
    ("status", "entity", "path_entity", "token", "body", "code", "contains", "patch"), POST_CASES
)
def test_submit_signature(
    status: str,
    entity: dict[str, Any],
    path_entity: str,
    token: str,
    body: dict[str, Any],
    code: int,
    contains: str | None,
    patch: dict[str, Any] | None,
) -> None:
    record_id = str(uuid4())
    client, repo = _app({record_id: {"status": status}}, entity=entity)
    resp = client.post(
        f"/api/sign/{path_entity}/{record_id}",
        json={"token": _token(token, record_id), "signatory_name": "Alice", **body},
    )
    assert resp.status_code == code, resp.text
    if contains:
        assert contains in resp.text
    _assert_patch(repo, patch)


def test_pdf_stack_signing_error_carries_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1377: a SigningError from the PDF stack (e.g. the [signing] extra is
    missing) surfaces its actionable message, not a bare Internal Server Error."""

    def missing_extra(*args: Any, **kwargs: Any) -> bytes:
        raise SigningError(
            "fpdf2 is not installed. Install with `pip install dazzle-dsl[signing]`."
        )

    monkeypatch.setattr("dazzle.signing.routes.generate_pdf", missing_extra)
    record_id = str(uuid4())
    client, repo = _app({record_id: {"status": "viewed"}})
    resp = client.post(
        f"/api/sign/Contract/{record_id}",
        json={"token": _token("valid", record_id), "signatory_name": "Alice"},
    )
    assert resp.status_code == 500
    assert "dazzle-dsl[signing]" in resp.json()["detail"]
    assert repo.update_calls == []


# ---------------------------------------------------------------------
# Full happy-path sign (needs the [signing] extra)
# ---------------------------------------------------------------------


def _sign(client: TestClient, record_id: str, token: str | None = None, **body: Any) -> Any:
    token = token or _token("valid", record_id)
    return client.post(
        f"/api/sign/Contract/{record_id}",
        json={"token": token, "signatory_name": "Alice", **body},
    )


@pytest.mark.usefixtures("signing_cert_env")
class TestFullSignFlow:
    def test_sign_returns_signed_pdf_and_marks_row_signed(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (60, 30), color="white").save(buf, format="PNG")
        record_id = str(uuid4())
        client, repo = _app({record_id: {"status": "viewed"}})
        resp = _sign(client, record_id, signature_png_b64=base64.b64encode(buf.getvalue()).decode())
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        disposition = resp.headers["content-disposition"]
        assert f'filename="contract-{record_id}.pdf"' in disposition  # slug, not entity name
        assert resp.content.startswith(b"%PDF-")
        _assert_patch(
            repo, {"status": "signed", "signed_at": PRESENT, "signing_token_hash": PRESENT}
        )
        assert "signed_document" not in repo.update_calls[0][1]  # no file service wired

    def test_sign_persists_pdf_through_file_service(self) -> None:
        record_id = str(uuid4())
        files = _MockFileService()
        client, repo = _app({record_id: {"status": "viewed"}}, file_service=files)
        assert _sign(client, record_id).status_code == 200
        [upload] = files.uploads
        assert upload["size"] > 100
        assert {k: v for k, v in upload.items() if k != "size"} == {
            "filename": f"contract-{record_id}.pdf",
            "content_type": "application/pdf",
            "entity_name": "Contract",
            "entity_id": record_id,
            "field_name": "signed_document",
            "path_prefix": "signing/Contract",
        }
        _assert_patch(repo, {"signed_document": f"/files/contract-{record_id}.pdf"})

    def test_upload_failure_falls_back_to_durable_storage(self, tmp_path: Any) -> None:
        """TR-49: an upload/metadata failure still leaves a durable signed_document."""
        from dazzle.http.runtime.file_storage import LocalStorageBackend

        record_id = str(uuid4())
        files = _MockFileService(fail_upload=True)
        files.storage = LocalStorageBackend(tmp_path, "/files")
        client, repo = _app({record_id: {"status": "viewed"}}, file_service=files)
        # One token throughout: the completion page and signed-copy match on
        # its hash, and a re-mint in a later second would differ.
        token = _token("valid", record_id)
        assert _sign(client, record_id, token).status_code == 200
        _assert_patch(repo, {"status": "signed"})
        assert str(repo.update_calls[0][1]["signed_document"]).startswith("/files/")

        params = {"token": token}
        page = client.get(f"/sign/Contract/{record_id}", params=params)
        assert "Download your signed copy" in page.text
        copy = client.get(f"/sign/Contract/{record_id}/signed-copy", params=params)
        assert copy.status_code == 200
        assert copy.headers["content-type"].startswith("application/pdf")
        assert f'filename="contract-{record_id}-signed.pdf"' in copy.headers["content-disposition"]
        assert copy.content.startswith(b"%PDF-")

    def test_signing_storage_writes_to_named_backend(self, tmp_path: Any) -> None:
        """#1816: ``[signing] storage`` puts the signed PDF in that object store,
        not on local disk, and the signed-copy link reads it back from there."""
        import asyncio

        from dazzle.http.runtime.file_storage import FileService, LocalStorageBackend
        from dazzle.http.runtime.storage import FakeStorageProvider, StorageRegistry
        from dazzle.http.runtime.storage.file_backend import (
            ProviderStorageBackend,
            storage_backend_name,
        )

        fake = FakeStorageProvider(name="signed_docs", prefix_template="production/signed/")
        registry = StorageRegistry()
        registry.register_provider("signed_docs", fake)
        named = ProviderStorageBackend(registry, "signed_docs")
        metadata: dict[str, Any] = {}
        store: Any = SimpleNamespace(
            save=lambda m: metadata.__setitem__(str(m.id), m),
            get=lambda file_id: metadata.get(str(file_id)),
        )
        shared = FileService(
            LocalStorageBackend(tmp_path, "/files"), store, backends={named.name: named}
        )
        files = shared.writing_to(storage_backend_name("signed_docs"))

        record_id = str(uuid4())
        client, repo = _app({record_id: {"status": "viewed"}}, file_service=files)
        token = _token("valid", record_id)
        assert _sign(client, record_id, token).status_code == 200

        [(key, body)] = fake.objects().items()
        assert key.startswith("production/signed/signing/Contract/")
        assert body.startswith(b"%PDF-")
        assert not list(tmp_path.rglob("*.pdf"))  # nothing on local disk
        url = repo.update_calls[0][1]["signed_document"]
        assert url.startswith("/api/storage/signed_docs/proxy?key=production/signed/")

        copy = client.get(f"/sign/Contract/{record_id}/signed-copy", params={"token": token})
        assert copy.status_code == 200
        assert copy.content == body
        # The shared service (file + document routes) routes reads by backend too.
        [meta] = metadata.values()
        assert asyncio.run(shared.download(meta.id))[0] == body

    @pytest.mark.parametrize(
        ("template", "code", "check"),
        [
            pytest.param(
                "custom_template",
                200,
                lambda r: b"CUSTOM TEMPLATE BODY MARKER" in r.content,
                id="callable-body-reaches-pdf",
            ),
            pytest.param(
                "non_str_template",
                500,
                lambda r: "must return str" in r.text,
                id="callable-must-return-str",
            ),
        ],
    )
    def test_signing_template_callable(self, template: str, code: int, check: Any) -> None:
        record_id = str(uuid4())
        client, _ = _app(
            {record_id: {"status": "viewed"}}, entity={"signing_template": f"{_MOD}.{template}"}
        )
        resp = _sign(client, record_id)
        assert resp.status_code == code
        assert check(resp)

    def test_custom_branding_reaches_both_pdf_stages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dazzle.signing import service
        from dazzle.signing.service import PdfBranding

        branding = PdfBranding(organisation="ACME LIMITED", footer_text="ACME | E&W")
        seen: dict[str, Any] = {}

        def spy_generate(*args: Any, **kwargs: Any) -> bytes:
            seen["generate"] = kwargs.get("branding")
            return service.generate_pdf(*args, **kwargs)

        async def spy_sign(*args: Any, **kwargs: Any) -> bytes:
            seen["sign"] = kwargs.get("branding")
            return await service.async_sign_pdf(*args, **kwargs)

        monkeypatch.setattr("dazzle.signing.routes.generate_pdf", spy_generate)
        monkeypatch.setattr("dazzle.signing.routes.async_sign_pdf", spy_sign)
        record_id = str(uuid4())
        client, _ = _app({record_id: {"status": "viewed"}}, branding=branding)
        assert _sign(client, record_id).status_code == 200
        assert seen == {"generate": branding, "sign": branding}


# ---------------------------------------------------------------------
# POST /sign/{entity}/{id}/resend — expired-link recovery (TR-53)
# ---------------------------------------------------------------------

RESEND_CASES = [
    # (row status, hook, token, status, page fragment, hook emails)
    pytest.param("sent", None, "expired", 404, None, [], id="no-hook-404"),
    pytest.param(
        "sent", "record_resend", "garbage", 403, None, [], id="tampered-token-403-no-send"
    ),
    pytest.param(
        "signed", "record_resend", "expired", 200, None, [], id="signed-doc-is-terminal-not-renewed"
    ),
    pytest.param(
        "sent", "async_record_resend", "expired", 200, None, [EMAIL], id="async-hook-is-awaited"
    ),
    pytest.param(
        "sent", "failing_resend", "expired", 500, "send a new link", [], id="hook-signing-error-500"
    ),
]


@pytest.mark.parametrize(("status", "hook", "token", "code", "contains", "sent_to"), RESEND_CASES)
def test_resend(
    status: str, hook: str | None, token: str, code: int, contains: str | None, sent_to: list[str]
) -> None:
    record_id = str(uuid4())
    client, repo = _app(
        {record_id: {"status": status}}, resend_hook=f"{_MOD}.{hook}" if hook else ""
    )
    resp = client.post(
        f"/sign/Contract/{record_id}/resend", data={"token": _token(token, record_id)}
    )
    assert resp.status_code == code
    if contains:
        assert contains in resp.text.lower()
    assert [c["email"] for c in _resend_calls] == sent_to
    assert repo.update_calls == []


@pytest.mark.parametrize(
    ("hook", "code"),
    [
        pytest.param("record_resend", 200, id="hook-success"),
        pytest.param("bare_raise_resend", 500, id="hook-non-signing-error-message-carries-url"),
    ],
)
def test_resend_never_leaks_fresh_token(hook: str, code: int) -> None:
    record_id = str(uuid4())
    client, repo = _app({record_id: {"status": "sent"}}, resend_hook=f"{_MOD}.{hook}")
    resp = client.post(
        f"/sign/Contract/{record_id}/resend",
        data={"token": mint_token(record_id, "signer@acme.example", expires_hours=-1)},
    )
    assert resp.status_code == code
    assert "token=" not in resp.text
    if hook == "record_resend":
        [call] = _resend_calls
        assert call["email"] == "signer@acme.example"
        assert "signer@acme.example" in resp.text
        assert call["signing_url"].split("token=")[1] not in resp.text
    assert repo.update_calls == []


# ---------------------------------------------------------------------
# #1571 — durable signed-copy retrieval and the completion page
# ---------------------------------------------------------------------


def _signed_app(
    *, status: str = "signed", with_document: bool = True
) -> tuple[TestClient, str, _MockFileService, str]:
    """A row signed with the returned token (reuse it: a re-mint differs)."""
    record_id = str(uuid4())
    files = _MockFileService(record_id=record_id)
    token = _token("valid", record_id)
    row = {
        "id": record_id,
        "status": status,
        "signing_token_hash": token_hash(token),
        "signed_document": f"/files/{files.file_id}/signed-copy.pdf" if with_document else None,
    }
    client, _ = _app({record_id: row}, file_service=files)
    return client, record_id, files, token


SIGNED_COPY_CASES = [
    pytest.param({}, "valid", 200, id="original-token-streams-persisted-pdf"),
    # A valid token whose hash is not the one the row was signed with.
    pytest.param({}, "other-email", 403, id="wrong-credential-403"),
    pytest.param({}, "other-record", 403, id="token-for-other-record-403"),
    pytest.param({"status": "sent"}, "valid", 409, id="unsigned-record-409"),
    pytest.param({"with_document": False}, "valid", 404, id="no-persisted-copy-404"),
]


@pytest.mark.parametrize(("setup", "token", "code"), SIGNED_COPY_CASES)
def test_signed_copy(setup: dict[str, Any], token: str, code: int) -> None:
    client, record_id, files, signed_with = _signed_app(**setup)
    tok = signed_with if token == "valid" else _token(token, record_id)
    resp = client.get(f"/sign/Contract/{record_id}/signed-copy", params={"token": tok})
    assert resp.status_code == code
    if code == 200:
        assert resp.headers["content-type"].startswith("application/pdf")
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content == files.data
    elif code == 404:
        assert "unavailable" in resp.text


@pytest.mark.parametrize(
    ("setup", "token", "contains", "absent"),
    [
        pytest.param(
            {},
            "valid",
            ["Download your signed copy", "signed-copy"],
            [],
            id="completion-page-offers-download",
        ),
        pytest.param(
            {"with_document": False},
            "valid",
            ["Document signed"],
            ["Document unavailable", "signed-copy"],
            # TR-49: no regression to a dead end, and no broken download link.
            id="completion-page-without-persisted-copy-TR-49",
        ),
        pytest.param(
            {},
            "other-email",
            [],
            ["signed-copy"],
            id="non-matching-hash-gets-terminal-page-no-link",
        ),
    ],
)
def test_original_link_after_signing(
    setup: dict[str, Any], token: str, contains: list[str], absent: list[str]
) -> None:
    client, record_id, _, signed_with = _signed_app(**setup)
    tok = signed_with if token == "valid" else _token(token, record_id)
    resp = client.get(f"/sign/Contract/{record_id}", params={"token": tok})
    assert resp.status_code == 200
    for fragment in contains:
        assert fragment in resp.text, fragment
    for fragment in absent:
        assert fragment not in resp.text, fragment


# ---------------------------------------------------------------------
# #1385 — active states derive from the entity's status enum
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("enum_values", "expected"),
    [
        pytest.param(
            ["sent", "viewed", "signed", "declined", "expired"],
            {"sent", "viewed"},
            id="default-lifecycle",
        ),
        pytest.param(
            ["pending", "signed", "withdrawn", "expired"], {"pending"}, id="custom-lifecycle"
        ),
        pytest.param(None, {"sent", "viewed"}, id="no-status-field-defaults"),
    ],
)
def test_active_signing_states(enum_values: list[str] | None, expected: set[str]) -> None:
    entity = _entity()
    if enum_values is not None:
        status = FieldSpec(
            name="status", type=FieldType(kind=FieldTypeKind.ENUM, enum_values=enum_values)
        )
        entity = entity.model_copy(update={"fields": [*entity.fields, status]})
    assert _active_signing_states(entity) == frozenset(expected)


# ---------------------------------------------------------------------
# #1656 — shared-schema RLS bind for unauthenticated token links
# ---------------------------------------------------------------------

_HOST_ID = uuid4()
_TRUST_ID = str(uuid4())


def _middleware(tenant: ResolvedTenant | None, session_tenant: str | None) -> type:
    class _Attach(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            request.state.tenant = tenant
            if session_tenant:
                set_current_tenant_id(session_tenant)
            return await call_next(request)

    return _Attach


@pytest.mark.parametrize(
    ("tenant", "session_tenant", "bound_at_read"),
    [
        pytest.param(
            ResolvedTenant(kind="Practice", id=_HOST_ID, slug="acme", ancestor_ids=()),
            None,
            str(_HOST_ID),
            id="flat-host-binds-host-id",
        ),
        pytest.param(
            ResolvedTenant(kind="School", id=_HOST_ID, slug="north", ancestor_ids=(_TRUST_ID,)),
            None,
            _TRUST_ID,
            id="hierarchical-host-binds-partition-root-not-leaf",
        ),
        pytest.param(
            ResolvedTenant(kind="Practice", id=_HOST_ID, slug="acme", ancestor_ids=()),
            "session-tenant",
            "session-tenant",
            id="session-tenant-already-bound-wins",
        ),
    ],
)
def test_get_binds_rls_tenant_before_repo_read(
    tenant: ResolvedTenant | None, session_tenant: str | None, bound_at_read: str | None
) -> None:
    record_id = str(uuid4())
    client, repo = _app(
        {record_id: {"status": "viewed"}}, middleware=_middleware(tenant, session_tenant)
    )
    resp = client.get(f"/sign/Contract/{record_id}", params={"token": _token("valid", record_id)})
    assert resp.status_code == 200
    assert repo.tenant_ids_at_read == [bound_at_read]


@pytest.mark.parametrize(
    ("tenant", "inside"),
    [
        pytest.param(
            SimpleNamespace(id="practice-9", ancestor_ids=()), "practice-9", id="binds-host"
        ),
        pytest.param(None, None, id="no-host-no-bind"),
        pytest.param(SimpleNamespace(), None, id="host-without-id-no-bind"),
    ],
)
def test_rls_bind_is_scoped_to_the_block(tenant: Any, inside: str | None) -> None:
    """The bind lives only inside the ``with`` block — a pooled connection
    must not carry a token-link tenant into the next request."""
    token = set_current_tenant_id(None)  # type: ignore[arg-type]  # isolate from leaked binds
    try:
        with _signing_rls_tenant(SimpleNamespace(state=SimpleNamespace(tenant=tenant))):  # type: ignore[arg-type]
            assert get_current_tenant_id() == inside
        assert get_current_tenant_id() is None
    finally:
        token.var.reset(token)
