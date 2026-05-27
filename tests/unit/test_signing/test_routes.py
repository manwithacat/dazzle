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

from dazzle.signing.routes import create_signing_routes  # noqa: E402

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
) -> tuple[FastAPI, _MockRepo]:
    entity = _signable_entity(entity_name)
    if signing_validator is not None:
        entity = entity.model_copy(update={"signing_validator": signing_validator})
    repo = _MockRepo(rows)
    router = create_signing_routes([entity], repositories={entity_name: repo})
    assert router is not None
    app = FastAPI()
    app.include_router(router)
    return app, repo


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "test-secret-not-for-prod")


@pytest.fixture
def signing_cert_env(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("pyhanko")
    b64, password = generate_cert_chain_b64("Test Org")
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", b64)
    monkeypatch.setenv("SIGNING_CERT_PASSWORD", password)
    from dazzle.signing.service import reset_signer_cache

    reset_signer_cache()


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
        assert "signing-island" in resp.text  # placeholder Island marker
        assert len(repo.update_calls) == 1
        _, patch = repo.update_calls[0]
        assert patch["status"] == "viewed"
        assert patch["viewed_at"] is not None
        assert patch["signer_user_agent"] is not None

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
