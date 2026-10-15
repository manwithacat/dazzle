"""Tests for vendor mock server generator."""

from collections.abc import Callable
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


# Synthetic HMAC-auth pack. The routes are a stand-in, not a shipped vendor.


def _hmac_fields() -> dict:
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


def _hmac_pack() -> MagicMock:
    applicant_fm = _make_foreign_model(
        "Applicant", "id", _hmac_fields(), "A person undergoing verification"
    )
    ops = [
        _make_operation("create_applicant", "POST", "/resources/applicants?levelName={level_name}"),
        _make_operation("get_applicant", "GET", "/resources/applicants/{applicant_id}"),
        _make_operation("delete_applicant", "DELETE", "/resources/applicants/{applicant_id}"),
    ]
    auth = _make_auth("hmac")
    return _make_pack(
        name="hmac_vendor",
        provider="HmacVendor",
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
    def test_path_conversion_combined(self) -> None:
        """Combined: simple, with param, strips query string, semicolon param."""
        assert _path_to_fastapi("/resources/applicants") == "/resources/applicants"
        assert (
            _path_to_fastapi("/resources/applicants/{applicant_id}")
            == "/resources/applicants/{applicant_id}"
        )
        assert (
            _path_to_fastapi("/resources/applicants?levelName={level}") == "/resources/applicants"
        )
        result = _path_to_fastapi("/resources/applicants/-;externalUserId={external_user_id}")
        assert "{external_user_id}" in result
        assert "-;" not in result


class TestInferModel:
    def test_infer_model_combined(self) -> None:
        """Combined: matches by path, by op name, fallback single model, none."""
        fm_defs = {"Applicant": {"fields": {}}, "Document": {"fields": {}}}
        assert (
            _infer_model_for_operation("create", "/resources/applicants", "POST", fm_defs)
            == "Applicant"
        )
        assert (
            _infer_model_for_operation("get_document", "/resources/docs", "GET", fm_defs)
            == "Document"
        )
        single_def = {"Widget": {"fields": {}}}
        assert (
            _infer_model_for_operation("unknown", "/api/v1/things", "GET", single_def) == "Widget"
        )
        assert _infer_model_for_operation("health", "/health", "GET", fm_defs) is None


class TestExtractRecordId:
    def test_extract_record_id_combined(self) -> None:
        """Combined: id suffix param, id param, fallback last, returns None empty."""
        assert (
            _extract_record_id({"applicant_id": "abc123"}, "/resources/{applicant_id}") == "abc123"
        )
        assert _extract_record_id({"id": "xyz"}, "/items/{id}") == "xyz"
        assert _extract_record_id({"slug": "hello"}, "/items/{slug}") == "hello"
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

    def test_create_item(self, client: TestClient) -> None:
        resp = client.post("/items", json={"name": "Widget"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 1
        assert data["name"] == "Widget"

    @pytest.mark.parametrize(
        ("method", "body", "expected_name"),
        [
            pytest.param("GET", None, "Gadget", id="get"),
            pytest.param("PUT", {"name": "New"}, "New", id="update"),
        ],
    )
    def test_existing_item_round_trips(
        self, client: TestClient, method: str, body: dict | None, expected_name: str
    ) -> None:
        item_id = client.post("/items", json={"name": "Gadget"}).json()["id"]
        resp = client.request(method, f"/items/{item_id}", json=body)
        assert resp.status_code == 200
        assert resp.json()["name"] == expected_name

    @pytest.mark.parametrize(
        ("method", "body"),
        [
            pytest.param("GET", None, id="get"),
            pytest.param("PUT", {"name": "X"}, id="update"),
            pytest.param("DELETE", None, id="delete"),
        ],
    )
    def test_missing_item_returns_404(
        self, client: TestClient, method: str, body: dict | None
    ) -> None:
        assert client.request(method, "/items/999", json=body).status_code == 404

    def test_list_items(self, client: TestClient) -> None:
        client.post("/items", json={"name": "A"})
        client.post("/items", json={"name": "B"})
        resp = client.get("/items")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_delete_item(self, client: TestClient) -> None:
        create_resp = client.post("/items", json={"name": "Doomed"})
        item_id = create_resp.json()["id"]
        resp = client.delete(f"/items/{item_id}")
        assert resp.status_code == 200
        # Verify deletion
        get_resp = client.get(f"/items/{item_id}")
        assert get_resp.status_code == 404

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
    """Test mock server with request HMAC auth."""

    @pytest.fixture()
    def client(self) -> TestClient:
        from dazzle.testing.vendor_mock.generator import _build_app

        pack = _hmac_pack()
        app = _build_app(pack, seed=42)
        return TestClient(app, raise_server_exceptions=False)

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
# Integration tests: health and the auth gate across auth schemes
# ---------------------------------------------------------------------------


def _bearer_pack() -> MagicMock:
    record_fm = _make_foreign_model(
        "Record",
        "id",
        {
            "id": _make_field("uuid", required=True, pk=True),
            "title": _make_field("str(200)", required=True),
        },
    )
    return _make_pack(
        name="bearer_test",
        provider="BearerVendor",
        foreign_models=[record_fm],
        operations=[_make_operation("list_records", "GET", "/records")],
        auth=_make_auth("bearer"),
    )


def _api_key_pack() -> MagicMock:
    entry_fm = _make_foreign_model(
        "Entry",
        "id",
        {
            "id": _make_field("int", required=True, pk=True),
            "value": _make_field("str(50)", required=True),
        },
    )
    return _make_pack(
        name="apikey_test",
        provider="ApiKeyVendor",
        foreign_models=[entry_fm],
        operations=[_make_operation("list_entries", "GET", "/entries")],
        auth=_make_auth("api_key", header="X-API-Key"),
    )


# The API-key pack runs with specific token validation configured.
_API_KEY_TOKENS = {"api_key": "secret-key-123"}
_HMAC_HEADERS = {
    "X-App-Token": "test-token",
    "X-App-Access-Ts": "1700000000",
    "X-App-Access-Sig": "dummy-sig",
}


def _client(pack: MagicMock, auth_tokens: dict[str, str] | None = None) -> TestClient:
    from dazzle.testing.vendor_mock.generator import _build_app

    app = _build_app(pack, seed=1, auth_tokens=auth_tokens)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("pack", "auth_tokens", "provider"),
    [
        pytest.param(_noauth_pack, None, "Simple", id="no-auth"),
        pytest.param(_hmac_pack, None, "HmacVendor", id="hmac-bypasses-auth"),
        pytest.param(_bearer_pack, None, "BearerVendor", id="bearer-bypasses-auth"),
        pytest.param(_api_key_pack, _API_KEY_TOKENS, "ApiKeyVendor", id="api-key-bypasses-auth"),
    ],
)
def test_health_check_reports_provider_without_auth(
    pack: Callable[[], MagicMock], auth_tokens: dict[str, str] | None, provider: str
) -> None:
    resp = _client(pack(), auth_tokens).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "provider": provider}


@pytest.mark.parametrize(
    ("pack", "auth_tokens", "method", "path", "headers", "expected_status"),
    [
        pytest.param(_hmac_pack, None, "POST", "/resources/applicants", {}, 401, id="hmac-missing"),
        # Without auth_tokens configured, any correctly-formatted auth is accepted.
        pytest.param(
            _hmac_pack, None, "POST", "/resources/applicants", _HMAC_HEADERS, 201, id="hmac-valid"
        ),
        pytest.param(_bearer_pack, None, "GET", "/records", {}, 401, id="bearer-missing"),
        pytest.param(
            _bearer_pack,
            None,
            "GET",
            "/records",
            {"Authorization": "Bearer test-token"},
            200,
            id="bearer-valid",
        ),
        pytest.param(
            _bearer_pack,
            None,
            "GET",
            "/records",
            {"Authorization": "Basic dGVzdDp0ZXN0"},
            401,
            id="bearer-wrong-format",
        ),
        pytest.param(
            _api_key_pack,
            _API_KEY_TOKENS,
            "GET",
            "/entries",
            {"X-API-Key": "secret-key-123"},
            200,
            id="api-key-correct",
        ),
        pytest.param(
            _api_key_pack, _API_KEY_TOKENS, "GET", "/entries", {}, 401, id="api-key-missing"
        ),
        pytest.param(
            _api_key_pack,
            _API_KEY_TOKENS,
            "GET",
            "/entries",
            {"X-API-Key": "wrong-key"},
            401,
            id="api-key-wrong",
        ),
    ],
)
def test_auth_gate_status(
    pack: Callable[[], MagicMock],
    auth_tokens: dict[str, str] | None,
    method: str,
    path: str,
    headers: dict[str, str],
    expected_status: int,
) -> None:
    body = {"type": "individual"} if method == "POST" else None
    resp = _client(pack(), auth_tokens).request(method, path, headers=headers, json=body)
    assert resp.status_code == expected_status


# ---------------------------------------------------------------------------
# Test create_mock_server() with real API pack
# ---------------------------------------------------------------------------


class TestCreateMockServerFromPack:
    """Test creating a mock server from an actual API pack TOML file."""

    def test_stripe_pack_creates_app(self) -> None:
        app = create_mock_server("stripe_payments", seed=1)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "Stripe"

    def test_stripe_pack_has_routes(self) -> None:
        app = create_mock_server("stripe_payments", seed=1)
        from dazzle.http.runtime.route_validator import route_paths as _route_paths

        route_paths = _route_paths(app)
        assert "/health" in route_paths
        assert any("payment_intent" in p for p in route_paths)

    def test_unknown_pack_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            create_mock_server("nonexistent_pack_xyz")

    def test_store_accessible(self) -> None:
        app = create_mock_server("stripe_payments", seed=1)
        assert app.state.store is not None
        assert app.state.request_log is not None
        assert app.state.pack is not None
