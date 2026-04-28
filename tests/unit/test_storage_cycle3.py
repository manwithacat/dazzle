"""Tests for #932 cycle 3 — validator + upload-ticket auto-routes.

Cycle 3 ships:
- `validate_storage_refs(appspec, storage_defs)` — fails fast if a
  field's `storage=<name>` doesn't resolve to a declared block.
- `register_upload_ticket_routes(app, appspec, registry)` — auto-
  generates `POST /api/{entity}/upload-ticket` for every entity with
  at least one file-typed field bound to a storage.

Routes are tested via FastAPI's TestClient with `FakeStorageProvider`
injected through the registry. No real boto3, no moto — those are
covered in cycle 2's tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.manifest import StorageConfig
from dazzle.core.validator import validate_storage_refs
from dazzle_back.runtime.storage import (
    FakeStorageProvider,
    StorageRegistry,
    register_upload_ticket_routes,
)

# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _appspec_from_dsl(dsl: str):
    """Parse DSL and lift the fragment to a minimal AppSpec for
    validation. We bypass the linker since we only need
    `appspec.domain.entities` for storage validation."""
    from dazzle.core import ir

    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return ir.AppSpec(
        name="test_app",
        domain=ir.DomainSpec(entities=fragment.entities),
    )


def _config(name: str, **overrides: object) -> StorageConfig:
    base = {
        "backend": "s3",
        "bucket": "b",
        "region": "r",
        "prefix_template": "uploads/{user_id}/{record_id}/",
        "max_bytes": 1024,
        "content_types": [],
        "ticket_ttl_seconds": 60,
    }
    base.update(overrides)
    return StorageConfig(name=name, **base)  # type: ignore[arg-type]


class TestValidateStorageRefs:
    def test_valid_reference_passes(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
"""
        )
        errors, warnings = validate_storage_refs(spec, {"cohort_pdfs": _config("cohort_pdfs")})
        assert errors == []
        assert warnings == []

    def test_unresolved_reference_errors(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=missing_storage
"""
        )
        errors, _ = validate_storage_refs(spec, {})
        assert len(errors) == 1
        assert "storage='missing_storage'" in errors[0]
        assert "missing_storage" in errors[0]

    def test_error_lists_available_storages(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=typo
"""
        )
        errors, _ = validate_storage_refs(
            spec,
            {
                "cohort_pdfs": _config("cohort_pdfs"),
                "report_attachments": _config("report_attachments"),
            },
        )
        assert "['cohort_pdfs', 'report_attachments']" in errors[0]

    def test_storage_on_non_file_field_warns(self) -> None:
        """`storage=` on a non-file field is meaningless. Currently
        the parser doesn't reject it (the binding lives on FieldSpec
        regardless of type), but the validator surfaces it as a
        warning."""
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  notes: str(200) storage=cohort_pdfs
"""
        )
        errors, warnings = validate_storage_refs(spec, {"cohort_pdfs": _config("cohort_pdfs")})
        assert errors == []
        assert len(warnings) == 1
        assert "only applies to `file` typed fields" in warnings[0]

    def test_no_storage_no_validation(self) -> None:
        """Entities without storage references skip validation
        entirely — no errors when storage_defs is empty."""
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  notes: str(200)
"""
        )
        errors, warnings = validate_storage_refs(spec, {})
        assert errors == []
        assert warnings == []


# ---------------------------------------------------------------------------
# Auto-route registration
# ---------------------------------------------------------------------------

fastapi = pytest.importorskip("fastapi", reason="needs fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _wire_test_app(dsl: str, *, registry: StorageRegistry) -> tuple[FastAPI, list[str]]:
    spec = _appspec_from_dsl(dsl)
    app = FastAPI()
    paths = register_upload_ticket_routes(app=app, appspec=spec, registry=registry)
    return app, paths


def _registry_with_fake(
    name: str = "cohort_pdfs", **kwargs
) -> tuple[StorageRegistry, FakeStorageProvider]:
    fake = FakeStorageProvider(
        name=name,
        prefix_template=kwargs.get("prefix_template", "uploads/{user_id}/{record_id}/"),
        content_types=kwargs.get("content_types", []),
        max_bytes=kwargs.get("max_bytes", 50 * 1024 * 1024),
    )
    reg = StorageRegistry()
    reg.register_provider(name, fake)
    return reg, fake


def _authed_client(app: FastAPI, user_id: str = "user-abc") -> TestClient:
    """Return a TestClient with a stub auth_store registered so
    `current_user_id(request)` resolves to *user_id*."""
    from unittest.mock import MagicMock
    from uuid import UUID

    from dazzle_back.runtime.auth import register_auth_store
    from dazzle_back.runtime.auth.models import AuthContext, UserRecord

    user = UserRecord(
        id=UUID("00000000-0000-0000-0000-" + user_id.encode().hex().ljust(12, "0")[:12])
        if len(user_id) <= 6
        else UUID("12345678-1234-5678-1234-567812345678"),
        email="t@example.com",
        password_hash="$2b$12$test-hash-not-real-just-fixture-padding-here-ok",
    )
    ctx = AuthContext(
        user=user,
        is_authenticated=True,
        roles=["role_teacher"],
    )
    store = MagicMock()
    store.validate_session.return_value = ctx
    register_auth_store(store)

    client = TestClient(app)
    client.cookies.set("dazzle_session", "valid-session-id")
    return client


@pytest.fixture(autouse=True)
def _reset_auth_store():
    from dazzle_back.runtime.auth import register_auth_store

    yield
    register_auth_store(None)


class TestUploadTicketRoute:
    def test_registers_route_for_storage_field(self) -> None:
        reg, _ = _registry_with_fake()
        app, paths = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
""",
            registry=reg,
        )
        assert paths == ["/api/doc/upload-ticket"]

    def test_no_route_for_entity_without_storage_field(self) -> None:
        reg = StorageRegistry()
        app, paths = _wire_test_app(
            """
module test
app A "A"

entity Plain:
  id: uuid pk
  notes: str(200)
""",
            registry=reg,
        )
        assert paths == []

    def test_unauthenticated_returns_401(self) -> None:
        reg, _ = _registry_with_fake()
        app, _ = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
""",
            registry=reg,
        )
        client = TestClient(app)
        # No `register_auth_store` call → no auth resolves.
        resp = client.post("/api/doc/upload-ticket", json={"filename": "x.pdf"})
        assert resp.status_code == 401

    def test_authed_mints_ticket(self) -> None:
        reg, fake = _registry_with_fake()
        app, _ = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
""",
            registry=reg,
        )
        client = _authed_client(app)
        resp = client.post(
            "/api/doc/upload-ticket",
            json={"filename": "scan.pdf", "content_type": "application/pdf"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["storage"] == "cohort_pdfs"
        assert data["field"] == "source_pdf"
        assert data["s3_key"].endswith("scan.pdf")
        assert "{user_id}" not in data["s3_key"]  # interpolated
        assert "{record_id}" not in data["s3_key"]
        assert data["upload"]["url"].startswith("https://fake-storage.local")
        assert "Content-Type" in data["upload"]["fields"]
        # The fake captured the ticket — assert the key matches.
        assert fake.minted_tickets[0].s3_key == data["s3_key"]

    def test_filename_traversal_sanitised(self) -> None:
        reg, _ = _registry_with_fake()
        app, _ = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
""",
            registry=reg,
        )
        client = _authed_client(app)
        resp = client.post(
            "/api/doc/upload-ticket",
            json={
                "filename": "../../etc/passwd",
                "content_type": "application/pdf",
            },
        )
        assert resp.status_code == 200
        # Path traversal collapses to the basename, sanitised.
        assert "/etc/passwd" not in resp.json()["s3_key"]
        assert resp.json()["s3_key"].endswith("passwd")

    def test_content_type_not_allowed(self) -> None:
        reg, _ = _registry_with_fake(content_types=["application/pdf"])
        app, _ = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
""",
            registry=reg,
        )
        client = _authed_client(app)
        resp = client.post(
            "/api/doc/upload-ticket",
            json={"filename": "evil.exe", "content_type": "application/x-msdownload"},
        )
        assert resp.status_code == 400
        assert "content_type not allowed" in resp.json()["error"]

    def test_unconfigured_storage_returns_503(self) -> None:
        # Registry has the field's storage in `configs` but no
        # provider, AND no backend that can be built (we use a
        # bogus backend in the config).
        reg = StorageRegistry(configs={"cohort_pdfs": _config("cohort_pdfs", backend="azure_blob")})
        app, _ = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
""",
            registry=reg,
        )
        client = _authed_client(app)
        resp = client.post(
            "/api/doc/upload-ticket",
            json={"filename": "x.pdf", "content_type": "application/pdf"},
        )
        # Backend dispatch raises ValueError → 503.
        assert resp.status_code == 503

    def test_multi_field_dispatcher(self) -> None:
        """Entities with multiple storage-bound fields use a
        dispatcher that reads `body['field']` to pick the right
        binding."""
        fake1 = FakeStorageProvider(
            name="primary", prefix_template="primary/{user_id}/{record_id}/"
        )
        fake2 = FakeStorageProvider(name="thumbs", prefix_template="thumbs/{user_id}/{record_id}/")
        reg = StorageRegistry()
        reg.register_provider("primary", fake1)
        reg.register_provider("thumbs", fake2)

        app, paths = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=primary
  thumbnail: file storage=thumbs
""",
            registry=reg,
        )
        assert paths == ["/api/doc/upload-ticket"]
        client = _authed_client(app)
        # Pick `thumbnail`.
        resp = client.post(
            "/api/doc/upload-ticket",
            json={"field": "thumbnail", "filename": "preview.jpg", "content_type": "image/jpeg"},
        )
        assert resp.status_code == 200
        assert resp.json()["field"] == "thumbnail"
        assert resp.json()["storage"] == "thumbs"
        assert resp.json()["s3_key"].startswith("thumbs/")

    def test_multi_field_unknown_field_400(self) -> None:
        fake1 = FakeStorageProvider(name="primary")
        fake2 = FakeStorageProvider(name="thumbs")
        reg = StorageRegistry()
        reg.register_provider("primary", fake1)
        reg.register_provider("thumbs", fake2)
        app, _ = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=primary
  thumbnail: file storage=thumbs
""",
            registry=reg,
        )
        client = _authed_client(app)
        resp = client.post(
            "/api/doc/upload-ticket",
            json={"field": "nonexistent", "filename": "x", "content_type": "text/plain"},
        )
        assert resp.status_code == 400
        assert "unknown field" in resp.json()["error"]
        assert resp.json()["available"] == ["source_pdf", "thumbnail"]
