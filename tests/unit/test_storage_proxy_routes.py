"""Tests for #942 cycle 1a — read-side storage proxy auto-routes.

The framework registers ``GET /api/storage/{storage_name}/proxy`` for
every storage referenced from at least one ``file storage=...`` field
in the AppSpec. The handler streams object bytes through the server
under cookie auth — no presigned download URLs leak to the browser.

Tests cover:
- Route registration (one per referenced storage; none for
  unreferenced storages even if declared in dazzle.toml)
- Auth gate (401 unauthenticated)
- Prefix sandbox (403 cross-user; passes for caller's own prefix)
- Object existence (404 missing)
- Provider read failure → 503
- Content-Type passthrough from provider metadata
- Content-Disposition: inline (browser-viewable, not a download)
- Shared-asset bucket (no ``{user_id}`` placeholder) — prefix
  accepts any key; #941 fan-in compatibility
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle_back.runtime.storage import (
    FakeStorageProvider,
    StorageRegistry,
    register_storage_proxy_routes,
)

fastapi = pytest.importorskip("fastapi", reason="needs fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures + harness
# ---------------------------------------------------------------------------


def _appspec_from_dsl(dsl: str) -> Any:
    from dazzle.core import ir

    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return ir.AppSpec(
        name="test_app",
        domain=ir.DomainSpec(entities=fragment.entities),
    )


def _wire_test_app(dsl: str, *, registry: StorageRegistry) -> tuple[FastAPI, list[str]]:
    spec = _appspec_from_dsl(dsl)
    app = FastAPI()
    paths = register_storage_proxy_routes(app=app, appspec=spec, registry=registry)
    return app, paths


def _registry_with_fake(
    name: str = "cohort_pdfs",
    prefix_template: str = "uploads/{user_id}/{record_id}/",
) -> tuple[StorageRegistry, FakeStorageProvider]:
    fake = FakeStorageProvider(name=name, prefix_template=prefix_template)
    reg = StorageRegistry()
    reg.register_provider(name, fake)
    return reg, fake


def _authed_client(app: FastAPI, user_id: str = "user-abc") -> TestClient:
    from unittest.mock import MagicMock
    from uuid import UUID

    from dazzle_back.runtime.auth import register_auth_store
    from dazzle_back.runtime.auth.models import AuthContext, UserRecord

    user = UserRecord(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        email="t@example.com",
        password_hash="$2b$12$test-hash-not-real-just-fixture-padding-here-ok",
    )
    ctx = AuthContext(user=user, is_authenticated=True, roles=["role_teacher"])
    store = MagicMock()
    store.validate_session.return_value = ctx
    register_auth_store(store)

    client = TestClient(app)
    client.cookies.set("dazzle_session", "valid-session-id")
    return client


@pytest.fixture(autouse=True)
def _reset_auth_store() -> Any:
    from dazzle_back.runtime.auth import register_auth_store

    yield
    register_auth_store(None)


# The user_id the auth fixture above resolves to, used by every test
# that constructs a sandbox-matching s3_key.
_AUTHED_UID = "12345678-1234-5678-1234-567812345678"


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    def test_registers_one_route_per_referenced_storage(self) -> None:
        reg, _ = _registry_with_fake()
        _, paths = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
""",
            registry=reg,
        )
        assert paths == ["/api/storage/cohort_pdfs/proxy"]

    def test_no_route_when_no_storage_fields(self) -> None:
        reg = StorageRegistry()
        _, paths = _wire_test_app(
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

    def test_dedupes_same_storage_referenced_by_multiple_fields(self) -> None:
        """An entity with two file fields backed by the same storage
        gets ONE proxy route — the proxy is per-storage, not per-field."""
        reg, _ = _registry_with_fake()
        _, paths = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
  thumbnail: file storage=cohort_pdfs
""",
            registry=reg,
        )
        assert paths == ["/api/storage/cohort_pdfs/proxy"]

    def test_multi_storage_field_registers_each_storage(self) -> None:
        """A field declared `storage=cohort_pdfs|starter_packs` (#941)
        registers BOTH proxy routes — clients pick the right one based
        on which prefix the s3_key matches."""
        reg = StorageRegistry()
        for name in ("cohort_pdfs", "starter_packs"):
            reg.register_provider(name, FakeStorageProvider(name=name))
        _, paths = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs|starter_packs
""",
            registry=reg,
        )
        assert sorted(paths) == [
            "/api/storage/cohort_pdfs/proxy",
            "/api/storage/starter_packs/proxy",
        ]


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


class TestAuthGate:
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
        # No _authed_client — naked TestClient with no session cookie.
        client = TestClient(app)
        resp = client.get(
            "/api/storage/cohort_pdfs/proxy",
            params={"key": "uploads/x/y/z.pdf"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Prefix sandbox + object existence
# ---------------------------------------------------------------------------


class TestPrefixSandbox:
    def test_caller_own_prefix_passes(self) -> None:
        reg, fake = _registry_with_fake()
        key = f"uploads/{_AUTHED_UID}/r1/file.pdf"
        fake.put_object(key, b"hello", content_type="application/pdf")

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
        resp = client.get("/api/storage/cohort_pdfs/proxy", params={"key": key})
        assert resp.status_code == 200
        assert resp.content == b"hello"
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["content-disposition"] == "inline"

    def test_other_users_prefix_403(self) -> None:
        reg, fake = _registry_with_fake()
        # Object exists but under a different user's prefix.
        fake.put_object(
            "uploads/other-user-id/r1/file.pdf",
            b"x",
            content_type="application/pdf",
        )
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
        resp = client.get(
            "/api/storage/cohort_pdfs/proxy",
            params={"key": "uploads/other-user-id/r1/file.pdf"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "outside_sandbox"

    def test_object_missing_returns_404(self) -> None:
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
        resp = client.get(
            "/api/storage/cohort_pdfs/proxy",
            params={"key": f"uploads/{_AUTHED_UID}/r1/never-uploaded.pdf"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "object_not_found"

    def test_missing_key_query_param_400(self) -> None:
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
        resp = client.get("/api/storage/cohort_pdfs/proxy")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "missing_key"


# ---------------------------------------------------------------------------
# Shared-asset bucket (#941 fan-in)
# ---------------------------------------------------------------------------


class TestSharedAssetBucket:
    def test_no_user_placeholder_accepts_any_key_under_prefix(self) -> None:
        """Starter-pack-style bucket: prefix_template carries no
        ``{user_id}`` placeholder. The sandbox accepts any key under
        the literal prefix — that's the intentional shape, the
        bucket is shared-read at the application layer (#941)."""
        reg, fake = _registry_with_fake(
            name="starter_packs",
            prefix_template="production/starter_packs/",
        )
        fake.put_object(
            "production/starter_packs/y10_macbeth.pdf",
            b"shared",
            content_type="application/pdf",
        )
        app, _ = _wire_test_app(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=starter_packs
""",
            registry=reg,
        )
        client = _authed_client(app)
        resp = client.get(
            "/api/storage/starter_packs/proxy",
            params={"key": "production/starter_packs/y10_macbeth.pdf"},
        )
        assert resp.status_code == 200
        assert resp.content == b"shared"


# ---------------------------------------------------------------------------
# Provider failure → 503
# ---------------------------------------------------------------------------


class TestProviderFailure:
    def test_get_object_raises_503(self) -> None:
        """If the provider's get_object raises (network error, auth
        failure, transient S3 issue), surface as 503 — distinguishes
        from 404 (object missing) so clients don't retry forever on
        an infra fault."""
        reg, fake = _registry_with_fake()
        key = f"uploads/{_AUTHED_UID}/r1/file.pdf"
        fake.put_object(key, b"x", content_type="application/pdf")

        def boom(_key: str) -> Any:
            raise RuntimeError("boto auth failed")

        fake.get_object = boom  # type: ignore[method-assign]

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
        resp = client.get("/api/storage/cohort_pdfs/proxy", params={"key": key})
        assert resp.status_code == 503
        assert resp.json()["detail"]["error"] == "storage_read_failed"

    def test_unconfigured_storage_returns_503(self) -> None:
        # Empty registry — entity declares storage=cohort_pdfs but
        # no provider is registered. Route still gets registered
        # (we only know what's referenced from DSL), but hitting it
        # 503s.
        reg = StorageRegistry()
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
        resp = client.get(
            "/api/storage/cohort_pdfs/proxy",
            params={"key": f"uploads/{_AUTHED_UID}/r1/x.pdf"},
        )
        assert resp.status_code == 503
        assert resp.json()["detail"]["error"] == "storage_unconfigured"


# ---------------------------------------------------------------------------
# Provider extension (get_object on protocol)
# ---------------------------------------------------------------------------


class TestProviderProtocol:
    def test_fake_get_object_returns_bytes(self) -> None:
        fake = FakeStorageProvider(name="x", prefix_template="p/")
        fake.put_object("p/file.pdf", b"abc", content_type="application/pdf")
        assert fake.get_object("p/file.pdf") == b"abc"

    def test_fake_get_object_returns_none_for_missing_key(self) -> None:
        fake = FakeStorageProvider(name="x", prefix_template="p/")
        assert fake.get_object("p/nope.pdf") is None
