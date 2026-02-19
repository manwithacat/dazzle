"""Tests for vendor mock server generator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dazzle.testing.vendor_mock.generator import (
    _extract_record_id,
    _infer_model_for_operation,
    _path_to_fastapi,
    create_mock_server,
)

# ---------------------------------------------------------------------------
# Helpers: build a minimal ApiPack mock for tests
# ---------------------------------------------------------------------------


def _make_field(
    type_str: str, *, required: bool = False, pk: bool = False, description: str = ""
) -> dict:
    d: dict = {"type": type_str}
    if required:
        d["required"] = True
    if pk:
        d["pk"] = True
    if description:
        d["description"] = description
    return d


def _make_foreign_model(name: str, key: str, fields: dict, description: str = "") -> MagicMock:
    fm = MagicMock()
    fm.name = name
    fm.key_field = key
    fm.fields = fields
    fm.description = description
    return fm


def _make_operation(name: str, method: str, path: str, description: str = "") -> MagicMock:
    op = MagicMock()
    op.name = name
    op.method = method
    op.path = path
    op.description = description or name
    return op


def _make_auth(auth_type: str, header: str | None = None, prefix: str | None = None) -> MagicMock:
    auth = MagicMock()
    auth.auth_type = auth_type
    auth.header = header
    auth.prefix = prefix
    return auth


def _make_pack(
    *,
    name: str = "test_pack",
    provider: str = "TestVendor",
    foreign_models: list | None = None,
    operations: list | None = None,
    auth: MagicMock | None = None,
) -> MagicMock:
    pack = MagicMock()
    pack.name = name
    pack.provider = provider
    pack.foreign_models = foreign_models or []
    pack.operations = operations or []
    pack.auth = auth
    return pack


# Standard SumSub-like test fixtures


def _sumsub_fields() -> dict:
    return {
        "id": _make_field("str(50)", required=True, pk=True),
        "external_user_id": _make_field("str(100)"),
        "type": _make_field("enum[individual,company]", required=True),
        "email": _make_field("email"),
        "first_name": _make_field("str(100)"),
        "last_name": _make_field("str(100)"),
        "created_at": _make_field("datetime"),
        "updated_at": _make_field("datetime"),
    }


def _sumsub_pack() -> MagicMock:
    applicant_fm = _make_foreign_model(
        "Applicant", "id", _sumsub_fields(), "A person undergoing verification"
    )
    ops = [
        _make_operation("create_applicant", "POST", "/resources/applicants?levelName={level_name}"),
        _make_operation("get_applicant", "GET", "/resources/applicants/{applicant_id}"),
        _make_operation("delete_applicant", "DELETE", "/resources/applicants/{applicant_id}"),
    ]
    auth = _make_auth("hmac")
    return _make_pack(
        name="sumsub_kyc",
        provider="SumSub",
        foreign_models=[applicant_fm],
        operations=ops,
        auth=auth,
    )


def _noauth_pack() -> MagicMock:
    item_fm = _make_foreign_model(
        "Item",
        "id",
        {
            "id": _make_field("int", required=True, pk=True),
            "name": _make_field("str(100)", required=True),
        },
        "A simple item",
    )
    ops = [
        _make_operation("create_item", "POST", "/items"),
        _make_operation("get_item", "GET", "/items/{item_id}"),
        _make_operation("list_items", "GET", "/items"),
        _make_operation("update_item", "PUT", "/items/{item_id}"),
        _make_operation("delete_item", "DELETE", "/items/{item_id}"),
    ]
    return _make_pack(
        name="simple",
        provider="Simple",
        foreign_models=[item_fm],
        operations=ops,
        auth=None,
    )


# ---------------------------------------------------------------------------
# Unit tests: path conversion
# ---------------------------------------------------------------------------


class TestPathConversion:
    def test_simple_path(self) -> None:
        assert _path_to_fastapi("/resources/applicants") == "/resources/applicants"

    def test_path_with_param(self) -> None:
        assert (
            _path_to_fastapi("/resources/applicants/{applicant_id}")
            == "/resources/applicants/{applicant_id}"
        )

    def test_strips_query_string(self) -> None:
        assert (
            _path_to_fastapi("/resources/applicants?levelName={level}") == "/resources/applicants"
        )

    def test_semicolon_param(self) -> None:
        result = _path_to_fastapi("/resources/applicants/-;externalUserId={external_user_id}")
        assert "{external_user_id}" in result
        assert "-;" not in result


class TestInferModel:
    def test_matches_by_path(self) -> None:
        fm_defs = {"Applicant": {"fields": {}}, "Document": {"fields": {}}}
        assert (
            _infer_model_for_operation("create", "/resources/applicants", "POST", fm_defs)
            == "Applicant"
        )

    def test_matches_by_op_name(self) -> None:
        fm_defs = {"Applicant": {"fields": {}}, "Document": {"fields": {}}}
        assert (
            _infer_model_for_operation("get_document", "/resources/docs", "GET", fm_defs)
            == "Document"
        )

    def test_fallback_single_model(self) -> None:
        fm_defs = {"Widget": {"fields": {}}}
        assert _infer_model_for_operation("unknown", "/api/v1/things", "GET", fm_defs) == "Widget"

    def test_returns_none_no_match(self) -> None:
        fm_defs = {"Applicant": {"fields": {}}, "Document": {"fields": {}}}
        assert _infer_model_for_operation("health", "/health", "GET", fm_defs) is None


class TestExtractRecordId:
    def test_extracts_id_suffix_param(self) -> None:
        assert (
            _extract_record_id({"applicant_id": "abc123"}, "/resources/{applicant_id}") == "abc123"
        )

    def test_extracts_id_param(self) -> None:
        assert _extract_record_id({"id": "xyz"}, "/items/{id}") == "xyz"

    def test_fallback_last_param(self) -> None:
        assert _extract_record_id({"slug": "hello"}, "/items/{slug}") == "hello"

    def test_returns_none_empty(self) -> None:
        assert _extract_record_id({}, "/items") is None


# ---------------------------------------------------------------------------
# Integration tests: no-auth CRUD mock server
# ---------------------------------------------------------------------------


class TestNoAuthMockServer:
    """Test a simple mock server without authentication."""

    @pytest.fixture()
    def client(self) -> TestClient:
        from dazzle.testing.vendor_mock.generator import _build_app

        pack = _noauth_pack()
        app = _build_app(pack, seed=42)
        return TestClient(app)

    def test_health_check(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["provider"] == "Simple"

    def test_create_item(self, client: TestClient) -> None:
        resp = client.post("/items", json={"name": "Widget"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 1
        assert data["name"] == "Widget"

    def test_get_item(self, client: TestClient) -> None:
        create_resp = client.post("/items", json={"name": "Gadget"})
        item_id = create_resp.json()["id"]
        resp = client.get(f"/items/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Gadget"

    def test_get_missing_item(self, client: TestClient) -> None:
        resp = client.get("/items/999")
        assert resp.status_code == 404

    def test_list_items(self, client: TestClient) -> None:
        client.post("/items", json={"name": "A"})
        client.post("/items", json={"name": "B"})
        resp = client.get("/items")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_update_item(self, client: TestClient) -> None:
        create_resp = client.post("/items", json={"name": "Old"})
        item_id = create_resp.json()["id"]
        resp = client.put(f"/items/{item_id}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_update_missing_item(self, client: TestClient) -> None:
        resp = client.put("/items/999", json={"name": "X"})
        assert resp.status_code == 404

    def test_delete_item(self, client: TestClient) -> None:
        create_resp = client.post("/items", json={"name": "Doomed"})
        item_id = create_resp.json()["id"]
        resp = client.delete(f"/items/{item_id}")
        assert resp.status_code == 200
        # Verify deletion
        get_resp = client.get(f"/items/{item_id}")
        assert get_resp.status_code == 404

    def test_delete_missing_item(self, client: TestClient) -> None:
        resp = client.delete("/items/999")
        assert resp.status_code == 404

    def test_request_log(self, client: TestClient) -> None:
        client.post("/items", json={"name": "Logged"})
        client.get("/items")
        log = client.app.state.request_log  # type: ignore[union-attr]
        assert len(log) == 2
        assert log[0]["operation"] == "create_item"
        assert log[1]["operation"] == "list_items"


# ---------------------------------------------------------------------------
# Integration tests: HMAC-authenticated mock server
# ---------------------------------------------------------------------------


class TestHmacAuthMockServer:
    """Test mock server with HMAC auth (SumSub-style)."""

    @pytest.fixture()
    def client(self) -> TestClient:
        from dazzle.testing.vendor_mock.generator import _build_app

        pack = _sumsub_pack()
        app = _build_app(pack, seed=42)
        return TestClient(app, raise_server_exceptions=False)

    def test_health_bypasses_auth(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_missing_auth_returns_401(self, client: TestClient) -> None:
        resp = client.post("/resources/applicants", json={"type": "individual"})
        assert resp.status_code == 401

    def test_valid_hmac_headers_accepted(self, client: TestClient) -> None:
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers={
                "X-App-Token": "test-token",
                "X-App-Access-Ts": "1700000000",
                "X-App-Access-Sig": "dummy-sig",
            },
        )
        # Without auth_tokens configured, any correctly-formatted auth is accepted
        assert resp.status_code == 201

    def test_create_and_get_applicant(self, client: TestClient) -> None:
        headers = {
            "X-App-Token": "test-token",
            "X-App-Access-Ts": "1700000000",
            "X-App-Access-Sig": "dummy",
        }
        create_resp = client.post(
            "/resources/applicants",
            json={"type": "individual", "email": "test@example.com"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        applicant_id = create_resp.json()["id"]
        assert applicant_id is not None

        get_resp = client.get(f"/resources/applicants/{applicant_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["email"] == "test@example.com"

    def test_delete_applicant(self, client: TestClient) -> None:
        headers = {
            "X-App-Token": "tok",
            "X-App-Access-Ts": "123",
            "X-App-Access-Sig": "sig",
        }
        create_resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=headers,
        )
        applicant_id = create_resp.json()["id"]
        del_resp = client.delete(f"/resources/applicants/{applicant_id}", headers=headers)
        assert del_resp.status_code == 200

        get_resp = client.get(f"/resources/applicants/{applicant_id}", headers=headers)
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests: bearer/api_key auth
# ---------------------------------------------------------------------------


class TestBearerAuthMockServer:
    """Test mock server with bearer token auth."""

    @pytest.fixture()
    def client(self) -> TestClient:
        from dazzle.testing.vendor_mock.generator import _build_app

        item_fm = _make_foreign_model(
            "Record",
            "id",
            {
                "id": _make_field("uuid", required=True, pk=True),
                "title": _make_field("str(200)", required=True),
            },
        )
        pack = _make_pack(
            name="bearer_test",
            provider="BearerVendor",
            foreign_models=[item_fm],
            operations=[_make_operation("list_records", "GET", "/records")],
            auth=_make_auth("bearer"),
        )
        app = _build_app(pack, seed=1)
        return TestClient(app, raise_server_exceptions=False)

    def test_missing_bearer_returns_401(self, client: TestClient) -> None:
        resp = client.get("/records")
        assert resp.status_code == 401

    def test_valid_bearer_accepted(self, client: TestClient) -> None:
        resp = client.get("/records", headers={"Authorization": "Bearer test-token"})
        assert resp.status_code == 200

    def test_wrong_format_returns_401(self, client: TestClient) -> None:
        resp = client.get("/records", headers={"Authorization": "Basic dGVzdDp0ZXN0"})
        assert resp.status_code == 401


class TestApiKeyAuthWithTokenValidation:
    """Test mock server with API key auth and specific token validation."""

    @pytest.fixture()
    def client(self) -> TestClient:
        from dazzle.testing.vendor_mock.generator import _build_app

        item_fm = _make_foreign_model(
            "Entry",
            "id",
            {
                "id": _make_field("int", required=True, pk=True),
                "value": _make_field("str(50)", required=True),
            },
        )
        pack = _make_pack(
            name="apikey_test",
            provider="ApiKeyVendor",
            foreign_models=[item_fm],
            operations=[_make_operation("list_entries", "GET", "/entries")],
            auth=_make_auth("api_key", header="X-API-Key"),
        )
        app = _build_app(pack, seed=1, auth_tokens={"api_key": "secret-key-123"})
        return TestClient(app, raise_server_exceptions=False)

    def test_correct_api_key_accepted(self, client: TestClient) -> None:
        resp = client.get("/entries", headers={"X-API-Key": "secret-key-123"})
        assert resp.status_code == 200

    def test_missing_api_key_returns_401(self, client: TestClient) -> None:
        resp = client.get("/entries")
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self, client: TestClient) -> None:
        resp = client.get("/entries", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test create_mock_server() with real API pack
# ---------------------------------------------------------------------------


class TestCreateMockServerFromPack:
    """Test creating a mock server from an actual API pack TOML file."""

    def test_sumsub_pack_creates_app(self) -> None:
        app = create_mock_server("sumsub_kyc", seed=1)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "SumSub"

    def test_sumsub_pack_has_routes(self) -> None:
        app = create_mock_server("sumsub_kyc", seed=1)
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in route_paths
        # Should have applicant routes
        assert any("applicant" in p for p in route_paths)

    def test_unknown_pack_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            create_mock_server("nonexistent_pack_xyz")

    def test_store_accessible(self) -> None:
        app = create_mock_server("sumsub_kyc", seed=1)
        assert app.state.store is not None
        assert app.state.request_log is not None
        assert app.state.pack is not None
