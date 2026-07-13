"""Tests for the auto-mounted signing routes (#1283 phase 3d).

Exercises the GET + POST handlers via FastAPI ``TestClient`` against a
hand-rolled async repository mock. The full DB/repo stack is out of
scope here; we verify the *contract* between the route layer and the
repository surface (`read`, `update`).
"""

from __future__ import annotations

import base64
import io
from typing import Any
from uuid import uuid4

import pytest

from dazzle.core.ir import EntitySpec
from dazzle.core.ir.fields import (
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
)
from dazzle.signing.cert import generate_cert_chain_b64
from dazzle.signing.tokens import mint_token

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dazzle.signing.routes import _resolve_document_body, create_signing_routes  # noqa: E402

# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


class _MockRepo:
    """Minimal async repository covering `read` + `update`."""

    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self.rows = rows
        self.update_calls: list[tuple[str, dict[str, Any]]] = []

    async def read(self, record_id: Any) -> dict[str, Any] | None:
        return self.rows.get(str(record_id))

    async def update(self, record_id: Any, data: dict[str, Any]) -> dict[str, Any]:
        self.update_calls.append((str(record_id), data))
        row = self.rows[str(record_id)]
        row.update(data)
        return row


def _signable_entity(name: str = "Contract") -> EntitySpec:
    return EntitySpec(
        name=name,
        title=name,
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
        ],
        signable=True,
    )


def _app_with_routes(
    rows: dict[str, dict[str, Any]],
    *,
    entity_name: str = "Contract",
    signing_validator: str | None = None,
    signing_template: str | None = None,
    file_service: Any | None = None,
    branding: Any | None = None,
    support_contact: str = "",
    resend_hook: str = "",
) -> tuple[FastAPI, _MockRepo]:
    entity = _signable_entity(entity_name)
    updates: dict[str, Any] = {}
    if signing_validator is not None:
        updates["signing_validator"] = signing_validator
    if signing_template is not None:
        updates["signing_template"] = signing_template
    if updates:
        entity = entity.model_copy(update=updates)
    repo = _MockRepo(rows)
    router = create_signing_routes(
        [entity],
        repositories={entity_name: repo},
        file_service=file_service,
        branding=branding,
        support_contact=support_contact,
        resend_hook=resend_hook,
    )
    assert router is not None
    app = FastAPI()
    app.include_router(router)
    return app, repo


class _MockFileService:
    """Minimal async file service. Records uploads + returns a fake URL."""

    def __init__(self, *, fail_upload: bool = False) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.fail_upload = fail_upload
        self.storage: Any = None
        self.metadata_store: Any = None

    async def upload(
        self,
        file: Any,
        filename: str,
        content_type: str | None = None,
        entity_name: str | None = None,
        entity_id: str | None = None,
        field_name: str | None = None,
        path_prefix: str = "",
    ) -> Any:
        from types import SimpleNamespace

        if self.fail_upload:
            raise RuntimeError("simulated FileService.upload failure (TR-49)")

        data = file.read()
        self.uploads.append(
            {
                "filename": filename,
                "content_type": content_type,
                "entity_name": entity_name,
                "entity_id": entity_id,
                "field_name": field_name,
                "path_prefix": path_prefix,
                "size": len(data),
            }
        )
        return SimpleNamespace(url=f"/files/{filename}")

    async def get_metadata(self, file_id: Any) -> Any:
        return None


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "test-secret-not-for-prod")


@pytest.fixture
def signing_cert_env(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("pyhanko")
    b64, password = generate_cert_chain_b64("Test Org")
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", b64)
    monkeypatch.setenv("SIGNING_CERT_PASSWORD", password)
    from dazzle.signing.service import _get_signer

    _get_signer.cache_clear()


# ---------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------


class TestRouterFactory:
    def test_returns_none_when_no_signable_entity(self) -> None:
        non_signable = EntitySpec(
            name="Other",
            title="Other",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
            ],
            signable=False,
        )
        router = create_signing_routes([non_signable], repositories={})
        assert router is None

    def test_returns_router_when_signable_entity_present(self) -> None:
        router = create_signing_routes([_signable_entity()], repositories={})
        assert router is not None


# ---------------------------------------------------------------------
# GET /sign/{entity}/{id}
# ---------------------------------------------------------------------


class TestRenderSigningPage:
    def test_missing_token_returns_400(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}})
        client = TestClient(app)
        resp = client.get(f"/sign/Contract/{record_id}")
        assert resp.status_code == 400
        assert "Missing signing token" in resp.text

    def test_invalid_token_returns_403(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}})
        client = TestClient(app)
        resp = client.get(f"/sign/Contract/{record_id}?token=not-real")
        assert resp.status_code == 403

    def test_token_record_mismatch_returns_403(self) -> None:
        record_id = str(uuid4())
        other_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}})
        client = TestClient(app)
        token = mint_token(other_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 403

    def test_unknown_record_returns_404(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 404

    def test_terminal_status_short_circuits(self) -> None:
        record_id = str(uuid4())
        app, repo = _app_with_routes({record_id: {"status": "signed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 200
        assert "already been signed" in resp.text
        # No write should have happened on a terminal-status GET.
        assert repo.update_calls == []

    def test_sent_transitions_to_viewed(self) -> None:
        record_id = str(uuid4())
        app, repo = _app_with_routes({record_id: {"status": "sent"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 200
        assert 'data-island="signing_pad"' in resp.text  # Island mount marker
        assert "/static/js/islands/signing-pad.js" in resp.text
        assert len(repo.update_calls) == 1
        _, patch = repo.update_calls[0]
        assert patch["status"] == "viewed"
        assert patch["viewed_at"] is not None
        assert patch["signer_user_agent"] is not None

    def test_get_page_shows_intended_signatory_email(self) -> None:
        """TR-15 transparency banner: the GET signing page surfaces the token's
        bound signatory email so a mis-delivered link (wrong inbox) is visible
        to the reader before they sign. Bearer links can't hard-gate identity;
        showing the intended recipient is the transparency safeguard."""
        record_id = str(uuid4())
        app, _repo = _app_with_routes({record_id: {"status": "sent"}})
        client = TestClient(app)
        token = mint_token(record_id, "devon.park@retailco.example")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 200
        assert "devon.park@retailco.example" in resp.text
        assert "intended for" in resp.text.lower()
        assert 'class="signing-intended-for"' in resp.text

    def test_viewed_status_no_redundant_transition(self) -> None:
        record_id = str(uuid4())
        app, repo = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 200
        # viewed → viewed should not write the row again.
        assert repo.update_calls == []

    def test_escapes_token_in_html(self) -> None:
        """Defence-in-depth: the token is HTML-escaped before it
        appears in a ``data-`` attribute. Tokens are HMAC base64 so
        they don't normally contain HTML chars; this guards against
        future token-shape changes."""
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        # The raw token contains "=" sometimes (padding); the attribute
        # value must be properly quote-escaped via &#x3d; or kept inside
        # the surrounding double-quotes.
        assert "<script>" not in resp.text


# ---------------------------------------------------------------------
# POST /api/sign/{entity}/{id}
# ---------------------------------------------------------------------


class TestSubmitSignature:
    def test_invalid_token_returns_403(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={"token": "not-real"},
        )
        assert resp.status_code == 403

    def test_terminal_status_returns_409(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "signed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={"token": token, "signatory_name": "Alice"},
        )
        assert resp.status_code == 409

    def test_decline_transitions_to_declined(self) -> None:
        record_id = str(uuid4())
        app, repo = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={"token": token, "decline": True, "decline_reason": "no"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "declined"}
        _, patch = repo.update_calls[0]
        assert patch["status"] == "declined"
        assert patch["signing_token_hash"]

    def test_signing_validator_can_block(self) -> None:
        """A validator that raises ``SigningError`` aborts the sign."""
        record_id = str(uuid4())
        # Use a real module + an injected function so the importlib
        # resolution actually returns something callable.
        import dazzle.signing.tokens as host

        def reject(*, entity: Any, row: Any) -> None:
            from dazzle.signing.tokens import SigningError

            raise SigningError("validator says no")

        host._test_validator_reject = reject  # type: ignore[attr-defined]
        try:
            app, repo = _app_with_routes(
                {record_id: {"status": "viewed"}},
                signing_validator="dazzle.signing.tokens._test_validator_reject",
            )
            client = TestClient(app)
            token = mint_token(record_id, "a@example.com")
            resp = client.post(
                f"/api/sign/Contract/{record_id}",
                json={"token": token, "signatory_name": "Alice"},
            )
            assert resp.status_code == 400
            assert "validator says no" in resp.text
            # No status mutation should have happened.
            assert repo.update_calls == []
        finally:
            del host._test_validator_reject  # type: ignore[attr-defined]

    def test_pdf_stack_signing_error_carries_detail(self) -> None:
        """#1377: a SigningError from the PDF generate/sign stack (e.g.
        the [signing] extra is not installed) must surface its actionable
        message, not escape as a bare {"detail": "Internal Server Error"}."""
        from unittest.mock import patch as mock_patch

        from dazzle.signing.tokens import SigningError

        record_id = str(uuid4())
        app, repo = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        with mock_patch(
            "dazzle.signing.routes.generate_pdf",
            side_effect=SigningError(
                "fpdf2 is not installed. Install with `pip install dazzle-dsl[signing]`."
            ),
        ):
            resp = client.post(
                f"/api/sign/Contract/{record_id}",
                json={"token": token, "signatory_name": "Alice"},
            )
        assert resp.status_code == 500
        assert "dazzle-dsl[signing]" in resp.json()["detail"]
        # No status mutation on a failed sign.
        assert repo.update_calls == []

    def test_signing_validator_dotted_path_must_be_valid(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes(
            {record_id: {"status": "viewed"}},
            signing_validator="UPPERCASE.NotAllowed.fn",
        )
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={"token": token, "signatory_name": "Alice"},
        )
        assert resp.status_code == 400
        assert "is not a valid dotted path" in resp.text

    def test_unknown_entity_returns_404(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.post(
            f"/api/sign/Otherwise/{record_id}",
            json={"token": token},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------
# Full happy-path sign (needs [signing] extra)
# ---------------------------------------------------------------------


@pytest.mark.usefixtures("signing_cert_env")
class TestFullSignFlow:
    def test_sign_produces_pdf_and_marks_signed(self) -> None:
        pytest.importorskip("fpdf")
        pytest.importorskip("pyhanko")
        from PIL import Image

        record_id = str(uuid4())
        app, repo = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        token = mint_token(record_id, "alice@example.com")

        # Build a tiny PNG signature so generate_pdf has something to
        # embed.
        buf = io.BytesIO()
        Image.new("RGB", (60, 30), color="white").save(buf, format="PNG")
        sig_b64 = base64.b64encode(buf.getvalue()).decode()

        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={
                "token": token,
                "signatory_name": "Alice Signer",
                "signature_png_b64": sig_b64,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF-")
        # Repo got the signed-state patch.
        assert len(repo.update_calls) == 1
        _, patch = repo.update_calls[0]
        assert patch["status"] == "signed"
        assert patch["signed_at"] is not None
        assert patch["signing_token_hash"]
        # No file_service was wired, so signed_document stays null.
        assert "signed_document" not in patch

    def test_sign_persists_pdf_when_file_service_set(self) -> None:
        pytest.importorskip("fpdf")
        pytest.importorskip("pyhanko")

        record_id = str(uuid4())
        file_service = _MockFileService()
        app, repo = _app_with_routes(
            {record_id: {"status": "viewed"}},
            file_service=file_service,
        )
        client = TestClient(app)
        token = mint_token(record_id, "alice@example.com")

        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={"token": token, "signatory_name": "Alice"},
        )
        assert resp.status_code == 200

        # File service got the signed PDF.
        assert len(file_service.uploads) == 1
        upload = file_service.uploads[0]
        assert upload["filename"] == f"Contract-{record_id}.pdf"
        assert upload["content_type"] == "application/pdf"
        assert upload["entity_name"] == "Contract"
        assert upload["entity_id"] == record_id
        assert upload["field_name"] == "signed_document"
        assert upload["path_prefix"] == "signing/Contract"
        assert upload["size"] > 100  # signed PDF, not empty

        # The entity row's signed_document field carries the URL.
        _, patch = repo.update_calls[0]
        assert patch["signed_document"] == f"/files/Contract-{record_id}.pdf"

    def test_sign_storage_fallback_when_upload_fails(self, tmp_path: Any) -> None:
        """TR-49: metadata/upload failure still leaves a durable signed_document URL."""
        pytest.importorskip("fpdf")
        pytest.importorskip("pyhanko")
        from dazzle.http.runtime.file_storage import LocalStorageBackend

        record_id = str(uuid4())
        file_service = _MockFileService(fail_upload=True)
        file_service.storage = LocalStorageBackend(tmp_path, "/files")
        app, repo = _app_with_routes(
            {record_id: {"status": "viewed"}},
            file_service=file_service,
        )
        client = TestClient(app)
        token = mint_token(record_id, "alice@example.com")

        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={"token": token, "signatory_name": "Alice"},
        )
        assert resp.status_code == 200
        _, patch = repo.update_calls[0]
        assert patch["status"] == "signed"
        url = patch.get("signed_document")
        assert url and str(url).startswith("/files/"), f"expected durable URL, got {url!r}"

        # Re-open completion page offers download CTA.
        open_resp = client.get(f"/sign/Contract/{record_id}", params={"token": token})
        assert open_resp.status_code == 200
        assert "Download your signed copy" in open_resp.text
        assert "signed-copy" in open_resp.text

        # Signed-copy endpoint serves PDF via storage fallback (no metadata).
        copy = client.get(f"/sign/Contract/{record_id}/signed-copy", params={"token": token})
        assert copy.status_code == 200
        assert copy.headers["content-type"].startswith("application/pdf")
        assert copy.content.startswith(b"%PDF-")

    def test_signing_template_provides_document_body(self) -> None:
        """When signing_template is set, the framework calls the project
        callable instead of using the stub placeholder body."""
        pytest.importorskip("fpdf")
        pytest.importorskip("pyhanko")

        import dazzle.signing.tokens as host

        marker = "<h1>CUSTOM TEMPLATE BODY MARKER</h1>"

        def render(*, entity: Any, row: Any) -> str:
            return marker

        host._test_template_render = render  # type: ignore[attr-defined]
        try:
            record_id = str(uuid4())
            app, _ = _app_with_routes(
                {record_id: {"status": "viewed"}},
                signing_template="dazzle.signing.tokens._test_template_render",
            )
            client = TestClient(app)
            token = mint_token(record_id, "alice@example.com")

            resp = client.post(
                f"/api/sign/Contract/{record_id}",
                json={"token": token, "signatory_name": "Alice"},
            )
            assert resp.status_code == 200
            assert resp.content.startswith(b"%PDF-")
            # The marker text appears in the PDF stream (fpdf2 may
            # compress, but Helvetica text strings stay readable for
            # ASCII inputs in the small-document case).
            assert b"CUSTOM TEMPLATE BODY MARKER" in resp.content
        finally:
            del host._test_template_render  # type: ignore[attr-defined]

    def test_signing_template_must_return_str(self) -> None:
        pytest.importorskip("fpdf")
        pytest.importorskip("pyhanko")
        import dazzle.signing.tokens as host

        def bad_render(*, entity: Any, row: Any) -> None:
            return None  # noqa: RET501 — intentional bad return

        host._test_template_bad = bad_render  # type: ignore[attr-defined]
        try:
            record_id = str(uuid4())
            app, _ = _app_with_routes(
                {record_id: {"status": "viewed"}},
                signing_template="dazzle.signing.tokens._test_template_bad",
            )
            client = TestClient(app)
            token = mint_token(record_id, "alice@example.com")

            resp = client.post(
                f"/api/sign/Contract/{record_id}",
                json={"token": token, "signatory_name": "Alice"},
            )
            assert resp.status_code == 500
            assert "must return str" in resp.text
        finally:
            del host._test_template_bad  # type: ignore[attr-defined]

    def test_custom_branding_flows_into_pdf_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A custom ``PdfBranding`` passed to ``create_signing_routes``
        reaches ``generate_pdf`` + ``async_sign_pdf`` unchanged. The
        PDF content stream is compressed so we can't grep it, but we
        can prove the branding is what the pipeline sees."""
        pytest.importorskip("fpdf")
        pytest.importorskip("pyhanko")
        from dazzle.signing import service as signing_service
        from dazzle.signing.service import PdfBranding

        record_id = str(uuid4())
        branding = PdfBranding(
            organisation="ACME LIMITED",
            organisation_tagline="Chartered Accountants",
            footer_text="ACME LIMITED | Registered in England & Wales",
            location="England and Wales",
        )

        captured: dict[str, Any] = {}
        real_generate_pdf = signing_service.generate_pdf
        real_async_sign_pdf = signing_service.async_sign_pdf

        def spy_generate_pdf(*args: Any, **kwargs: Any) -> bytes:
            captured["generate_branding"] = kwargs.get("branding")
            return real_generate_pdf(*args, **kwargs)

        async def spy_async_sign_pdf(*args: Any, **kwargs: Any) -> bytes:
            captured["sign_branding"] = kwargs.get("branding")
            return await real_async_sign_pdf(*args, **kwargs)

        # Patch the symbols the route handler imported at module load
        # time — those are the names create_signing_routes calls into.
        monkeypatch.setattr("dazzle.signing.routes.generate_pdf", spy_generate_pdf)
        monkeypatch.setattr("dazzle.signing.routes.async_sign_pdf", spy_async_sign_pdf)

        app, _ = _app_with_routes(
            {record_id: {"status": "viewed"}},
            branding=branding,
        )
        client = TestClient(app)
        token = mint_token(record_id, "alice@example.com")
        resp = client.post(
            f"/api/sign/Contract/{record_id}",
            json={"token": token, "signatory_name": "Alice"},
        )
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-")
        # Both pipeline stages saw the project-supplied branding,
        # not the framework default.
        assert captured["generate_branding"] is branding
        assert captured["sign_branding"] is branding


# ---------------------------------------------------------------------
# _resolve_document_body — unit tests for all three branches (#1287)
# ---------------------------------------------------------------------


class TestResolveDocumentBody:
    """Unit-level coverage for the three resolution branches."""

    def _make_entity(self, *, signing_template: str | None = None) -> EntitySpec:
        entity = _signable_entity("Contract")
        if signing_template is not None:
            entity = entity.model_copy(update={"signing_template": signing_template})
        return entity

    def test_signing_template_callable_wins(self) -> None:
        """Branch 1: signing_template callable is invoked and its return used."""
        from types import SimpleNamespace

        import dazzle.signing.tokens as host

        def render(*, entity: Any, row: Any) -> str:
            return "<p>custom template</p>"

        host._test_resolve_render = render  # type: ignore[attr-defined]
        try:
            entity = self._make_entity(
                signing_template="dazzle.signing.tokens._test_resolve_render"
            )
            row = SimpleNamespace(id=uuid4())
            result = _resolve_document_body(entity=entity, row=row, project_root=None)
            assert result == "<p>custom template</p>"
        finally:
            del host._test_resolve_render  # type: ignore[attr-defined]

    def test_file_template_used_when_present(self, tmp_path: Any) -> None:
        """Branch 2: file-based .html.j2 template is found and rendered."""
        from types import SimpleNamespace

        letters_dir = tmp_path / "templates" / "letters" / "Contract"
        letters_dir.mkdir(parents=True)
        (letters_dir / "default.html.j2").write_text("<p>Party: {{ row.party }}</p>")

        entity = self._make_entity()
        row = SimpleNamespace(id=uuid4(), party="ACME Ltd")
        result = _resolve_document_body(entity=entity, row=row, project_root=tmp_path)
        assert "<p>Party: ACME Ltd</p>" in result

    def test_stub_used_when_no_template_and_no_project_root(self) -> None:
        """Branch 3: stub fallback when project_root is None."""
        from types import SimpleNamespace

        entity = self._make_entity()
        row = SimpleNamespace(id=uuid4())
        result = _resolve_document_body(entity=entity, row=row, project_root=None)
        assert "placeholder" in result.lower() or "Contract" in result

    def test_stub_used_when_no_file_exists(self, tmp_path: Any) -> None:
        """Branch 3: stub fallback when project_root given but no file found."""
        from types import SimpleNamespace

        entity = self._make_entity()
        row = SimpleNamespace(id=uuid4())
        # tmp_path has no templates/letters/Contract/default.html.j2
        result = _resolve_document_body(entity=entity, row=row, project_root=tmp_path)
        assert "placeholder" in result.lower() or "Contract" in result


# ---------------------------------------------------------------------
# GET /sign — document body is present in server-rendered HTML (#1287)
# ---------------------------------------------------------------------


class TestGetPageEmbedDocumentBody:
    """The signing GET page must include the document body in server HTML."""

    def test_file_template_rendered_in_get_page(self, tmp_path: Any) -> None:
        """When a .html.j2 file exists, GET /sign embeds its rendered content.

        The mock repo returns a SimpleNamespace so getattr works, mirroring
        the Pydantic model rows returned by the real repository.
        """
        from types import SimpleNamespace

        letters_dir = tmp_path / "templates" / "letters" / "Contract"
        letters_dir.mkdir(parents=True)
        (letters_dir / "default.html.j2").write_text(
            "<p>Party: {{ row.party }}</p><p>Scope: {{ row.scope }}</p>"
        )

        record_id = str(uuid4())

        class _ModelRepo:
            """Repo that returns SimpleNamespace rows (like a Pydantic model)."""

            async def read(self, rid: Any) -> Any:
                return SimpleNamespace(
                    id=rid, status="viewed", party="Acme Corp", scope="Annual audit"
                )

            async def update(self, rid: Any, data: Any) -> None:
                pass

        entity = _signable_entity("Contract")
        router = create_signing_routes(
            [entity],
            repositories={"Contract": _ModelRepo()},
            project_root=tmp_path,
        )
        assert router is not None
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        from fastapi.testclient import TestClient

        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.text
        assert "Annual audit" in resp.text
        assert 'class="signing-document"' in resp.text

    def test_stub_shown_when_no_template(self) -> None:
        """Without a template file or callable, stub text appears in GET page."""
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "viewed"}})
        client = TestClient(app)
        token = mint_token(record_id, "a@example.com")
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 200
        # Stub body is still present; island is also present.
        assert 'class="signing-document"' in resp.text
        assert 'data-island="signing_pad"' in resp.text


# ---------------------------------------------------------------------
# Expired-link recovery (TR-53)
# ---------------------------------------------------------------------

# Module-level recorder so a dotted-path resend_hook resolves to a real
# callable (mirrors the validator-injection pattern above).
_resend_calls: list[dict[str, Any]] = []


def _record_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    _resend_calls.append(
        {"entity_name": entity_name, "row": row, "email": email, "signing_url": signing_url}
    )


async def _async_record_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    """An async hook — must be awaited directly, never run_until_complete'd
    on the already-running request loop."""
    _resend_calls.append({"email": email, "signing_url": signing_url})


def _failing_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    from dazzle.signing.tokens import SigningError

    raise SigningError("mail server down")


def _bare_raise_resend(*, entity_name: str, row: Any, email: str, signing_url: str) -> None:
    # A non-SigningError failure — must NOT leak signing_url via a traceback.
    raise ValueError(f"boom with {signing_url}")


_RESEND_OK = "tests.unit.test_signing.test_routes._record_resend"
_RESEND_ASYNC = "tests.unit.test_signing.test_routes._async_record_resend"
_RESEND_FAIL = "tests.unit.test_signing.test_routes._failing_resend"
_RESEND_BARE_RAISE = "tests.unit.test_signing.test_routes._bare_raise_resend"


class TestExpiredLinkRecovery:
    def setup_method(self) -> None:
        _resend_calls.clear()

    def _expired_token(self, record_id: str, email: str = "a@example.com") -> str:
        # Negative expires_hours → already expired but HMAC-valid.
        return mint_token(record_id, email, expires_hours=-1)

    def test_expired_link_with_hook_offers_resend_form(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}}, resend_hook=_RESEND_OK)
        client = TestClient(app)
        token = self._expired_token(record_id)
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 403
        assert "expired" in resp.text.lower()
        assert f"/sign/Contract/{record_id}/resend" in resp.text
        assert "Request a new signing link" in resp.text

    def test_expired_link_without_hook_shows_support_contact(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes(
            {record_id: {"status": "sent"}}, support_contact="help@acme.example"
        )
        client = TestClient(app)
        token = self._expired_token(record_id)
        resp = client.get(f"/sign/Contract/{record_id}?token={token}")
        assert resp.status_code == 403
        assert "expired" in resp.text.lower()
        assert "help@acme.example" in resp.text
        # No self-serve form without a hook.
        assert "/resend" not in resp.text

    def test_tampered_token_gets_plain_error_not_recovery(self) -> None:
        """A bad-HMAC token must NOT reach the recovery affordance."""
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}}, resend_hook=_RESEND_OK)
        client = TestClient(app)
        resp = client.get(f"/sign/Contract/{record_id}?token=garbage-token")
        assert resp.status_code == 403
        assert "Request a new signing link" not in resp.text

    def test_resend_invokes_hook_and_does_not_leak_token(self) -> None:
        record_id = str(uuid4())
        app, repo = _app_with_routes({record_id: {"status": "sent"}}, resend_hook=_RESEND_OK)
        client = TestClient(app)
        token = self._expired_token(record_id, "signer@acme.example")
        resp = client.post(f"/sign/Contract/{record_id}/resend", data={"token": token})
        assert resp.status_code == 200
        assert "signer@acme.example" in resp.text
        # Hook called exactly once, to the verified email.
        assert len(_resend_calls) == 1
        assert _resend_calls[0]["email"] == "signer@acme.example"
        # The freshly-minted token must NEVER appear in the HTTP response.
        fresh = _resend_calls[0]["signing_url"]
        new_token = fresh.split("token=")[1]
        assert new_token not in resp.text
        # Recovery does not mutate the document row.
        assert repo.update_calls == []

    def test_resend_without_hook_404s(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}})
        client = TestClient(app)
        token = self._expired_token(record_id)
        resp = client.post(f"/sign/Contract/{record_id}/resend", data={"token": token})
        assert resp.status_code == 404

    def test_resend_rejects_tampered_token(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}}, resend_hook=_RESEND_OK)
        client = TestClient(app)
        resp = client.post(f"/sign/Contract/{record_id}/resend", data={"token": "garbage"})
        assert resp.status_code == 403
        assert _resend_calls == []

    def test_resend_on_signed_doc_is_terminal_not_renewed(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "signed"}}, resend_hook=_RESEND_OK)
        client = TestClient(app)
        token = self._expired_token(record_id)
        resp = client.post(f"/sign/Contract/{record_id}/resend", data={"token": token})
        assert resp.status_code == 200
        assert _resend_calls == []  # already signed → nothing to renew

    def test_resend_hook_failure_surfaces_gracefully(self) -> None:
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}}, resend_hook=_RESEND_FAIL)
        client = TestClient(app)
        token = self._expired_token(record_id)
        resp = client.post(f"/sign/Contract/{record_id}/resend", data={"token": token})
        assert resp.status_code == 500
        assert "send a new link" in resp.text.lower()

    def test_async_resend_hook_is_awaited(self) -> None:
        """An async resend_hook must be awaited on the running loop, not
        run_until_complete'd (which RuntimeErrors inside the handler)."""
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}}, resend_hook=_RESEND_ASYNC)
        client = TestClient(app)
        token = self._expired_token(record_id, "async@acme.example")
        resp = client.post(f"/sign/Contract/{record_id}/resend", data={"token": token})
        assert resp.status_code == 200
        assert len(_resend_calls) == 1
        assert _resend_calls[0]["email"] == "async@acme.example"

    def test_non_signing_error_hook_does_not_leak_token(self) -> None:
        """A hook that raises a bare (non-SigningError) exception must be
        caught and produce the generic page — the fresh token must not
        reach the response even though the exception message contains it."""
        record_id = str(uuid4())
        app, _ = _app_with_routes({record_id: {"status": "sent"}}, resend_hook=_RESEND_BARE_RAISE)
        client = TestClient(app)
        token = self._expired_token(record_id)
        resp = client.post(f"/sign/Contract/{record_id}/resend", data={"token": token})
        assert resp.status_code == 500
        assert "send a new link" in resp.text.lower()
        assert "token=" not in resp.text  # no leaked signing_url


class TestActiveSigningStates:
    """#1385: active (still-signable / renewable) states derive from the
    entity's status enum, so custom lifecycles work — not a hard-coded tuple."""

    def _entity_with_status_enum(self, values: list[str]) -> EntitySpec:
        return EntitySpec(
            name="Doc",
            title="Doc",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="status", type=FieldType(kind=FieldTypeKind.ENUM, enum_values=values)
                ),
            ],
            signable=True,
        )

    def test_default_lifecycle_collapses_to_sent_viewed(self) -> None:
        from dazzle.signing.routes import _active_signing_states

        entity = self._entity_with_status_enum(["sent", "viewed", "signed", "declined", "expired"])
        assert _active_signing_states(entity) == frozenset({"sent", "viewed"})

    def test_custom_lifecycle_pending_is_active(self) -> None:
        from dazzle.signing.routes import _active_signing_states

        entity = self._entity_with_status_enum(["pending", "signed", "withdrawn", "expired"])
        assert _active_signing_states(entity) == frozenset({"pending"})

    def test_no_status_field_falls_back_to_default(self) -> None:
        from dazzle.signing.routes import _active_signing_states

        assert _active_signing_states(_signable_entity()) == frozenset({"sent", "viewed"})


# ---------------------------------------------------------------------
# #1571 — durable signed-copy retrieval + completion page
# ---------------------------------------------------------------------


class _CopyFileService(_MockFileService):
    """Extends the upload mock with the metadata/read_range surface the
    signed-copy route streams through (#1551 serve_bytes contract)."""

    def __init__(self, entity_name: str, entity_id: str) -> None:
        super().__init__()
        self.file_id = uuid4()
        self._entity_name = entity_name
        self._entity_id = entity_id
        self.data = b"%PDF-1.7 signed-copy-bytes"

    async def get_metadata(self, file_id: Any) -> Any:
        from types import SimpleNamespace

        if str(file_id) != str(self.file_id):
            return None
        return SimpleNamespace(
            id=self.file_id,
            size=len(self.data),
            content_type="application/pdf",
            filename="signed-copy.pdf",
            entity_name=self._entity_name,
            entity_id=self._entity_id,
        )

    async def read_range(self, file_id: Any, start: int, end: int) -> Any:
        chunk = self.data[start : end + 1]

        async def _aiter():
            yield chunk

        return _aiter(), len(chunk)


class TestSignedCopyRetrieval1571:
    """The durable retrieval path: the ORIGINAL signing token fetches the
    persisted signed PDF after signing; the original GET link lands on a
    completion page carrying that durable download instead of a dead end."""

    def _signed_setup(self, *, with_document: bool = True):
        from dazzle.signing.tokens import mint_token as _mint
        from dazzle.signing.tokens import token_hash as _hash

        record_id = str(uuid4())
        token = _mint(record_id, "devon@example.com")
        fs = _CopyFileService("Contract", record_id)
        row = {
            "id": record_id,
            "status": "signed",
            "signing_token_hash": _hash(token),
            "signed_document": f"/files/{fs.file_id}/signed-copy.pdf" if with_document else None,
        }
        app, repo = _app_with_routes({record_id: row}, file_service=fs)
        return TestClient(app), record_id, token, fs

    def test_signed_copy_streams_the_persisted_pdf(self) -> None:
        client, record_id, token, fs = self._signed_setup()
        resp = client.get(f"/sign/Contract/{record_id}/signed-copy", params={"token": token})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content == fs.data

    def test_wrong_credential_is_rejected(self) -> None:
        from dazzle.signing.tokens import mint_token as _mint

        client, record_id, _token, _fs = self._signed_setup()
        other = _mint(record_id, "attacker@example.com")  # valid token, wrong credential
        resp = client.get(f"/sign/Contract/{record_id}/signed-copy", params={"token": other})
        assert resp.status_code == 403

    def test_token_for_another_record_is_rejected(self) -> None:
        from dazzle.signing.tokens import mint_token as _mint

        client, record_id, _token, _fs = self._signed_setup()
        foreign = _mint(str(uuid4()), "devon@example.com")
        resp = client.get(f"/sign/Contract/{record_id}/signed-copy", params={"token": foreign})
        assert resp.status_code == 403

    def test_unsigned_record_is_409(self) -> None:
        from dazzle.signing.tokens import mint_token as _mint
        from dazzle.signing.tokens import token_hash as _hash

        record_id = str(uuid4())
        token = _mint(record_id, "devon@example.com")
        row = {"id": record_id, "status": "sent", "signing_token_hash": _hash(token)}
        app, _repo = _app_with_routes(
            {record_id: row}, file_service=_CopyFileService("Contract", record_id)
        )
        resp = TestClient(app).get(
            f"/sign/Contract/{record_id}/signed-copy", params={"token": token}
        )
        assert resp.status_code == 409

    def test_missing_persisted_copy_is_404_with_support_page(self) -> None:
        client, record_id, token, _fs = self._signed_setup(with_document=False)
        resp = client.get(f"/sign/Contract/{record_id}/signed-copy", params={"token": token})
        assert resp.status_code == 404
        assert "unavailable" in resp.text

    def test_original_link_lands_on_completion_page_with_durable_download(self) -> None:
        client, record_id, token, _fs = self._signed_setup()
        resp = client.get(f"/sign/Contract/{record_id}", params={"token": token})
        assert resp.status_code == 200
        assert "signed-copy" in resp.text  # the durable link
        assert "Download your signed copy" in resp.text

    def test_original_link_without_persisted_copy_still_completion_not_terminal(self) -> None:
        """TR-49: missing signed_document must not regress to 'Document unavailable'."""
        client, record_id, token, _fs = self._signed_setup(with_document=False)
        resp = client.get(f"/sign/Contract/{record_id}", params={"token": token})
        assert resp.status_code == 200
        assert "Document signed" in resp.text
        assert "Document unavailable" not in resp.text
        # No broken download CTA when the artifact was never persisted.
        assert "signed-copy" not in resp.text

    def test_original_link_without_matching_hash_stays_terminal(self) -> None:
        from dazzle.signing.tokens import mint_token as _mint

        client, record_id, _token, _fs = self._signed_setup()
        other = _mint(record_id, "someone-else@example.com")
        resp = client.get(f"/sign/Contract/{record_id}", params={"token": other})
        assert resp.status_code == 200
        assert "signed-copy" not in resp.text  # plain terminal page, no leak
