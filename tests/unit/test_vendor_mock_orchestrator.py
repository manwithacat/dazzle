"""Tests for vendor mock orchestrator."""

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dazzle.core.ir.services import APISpec, AuthProfile
from dazzle.testing.vendor_mock.orchestrator import (
    MockOrchestrator,
    _pack_to_env_var,
    discover_packs_from_appspec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_appspec(*api_specs: APISpec) -> MagicMock:
    """Create a minimal AppSpec mock with the given APIs."""
    appspec = MagicMock()
    appspec.apis = list(api_specs)
    return appspec


def _make_api(name: str, spec_inline: str | None = None) -> APISpec:
    """Create an APISpec with optional pack reference."""
    return APISpec(
        name=name,
        spec_inline=spec_inline,
        auth_profile=AuthProfile(kind="api_key_header"),
    )


# ---------------------------------------------------------------------------
# Unit tests: env var naming
# ---------------------------------------------------------------------------


class TestPackToEnvVar:
    def test_simple_name(self) -> None:
        assert _pack_to_env_var("companies_house_lookup") == "DAZZLE_API_COMPANIES_HOUSE_LOOKUP_URL"

    def test_hyphenated_name(self) -> None:
        assert _pack_to_env_var("my-vendor") == "DAZZLE_API_MY_VENDOR_URL"

    def test_dotted_name(self) -> None:
        assert _pack_to_env_var("hmrc.mtd") == "DAZZLE_API_HMRC_MTD_URL"


# ---------------------------------------------------------------------------
# Unit tests: pack discovery from AppSpec
# ---------------------------------------------------------------------------


class TestDiscoverPacks:
    def test_discovers_pack_refs(self) -> None:
        appspec = _make_appspec(
            _make_api("stripe", "pack:stripe_payments"),
            _make_api("companies_house", "pack:companies_house_lookup"),
        )
        packs = discover_packs_from_appspec(appspec)
        assert packs == ["stripe_payments", "companies_house_lookup"]

    def test_ignores_non_pack_specs(self) -> None:
        appspec = _make_appspec(
            _make_api("custom", None),
            _make_api("external", "https://api.example.com/openapi.json"),
        )
        packs = discover_packs_from_appspec(appspec)
        assert packs == []

    def test_deduplicates(self) -> None:
        appspec = _make_appspec(
            _make_api("stripe_v1", "pack:stripe_payments"),
            _make_api("stripe_v2", "pack:stripe_payments"),
        )
        packs = discover_packs_from_appspec(appspec)
        assert packs == ["stripe_payments"]

    def test_empty_appspec(self) -> None:
        appspec = _make_appspec()
        packs = discover_packs_from_appspec(appspec)
        assert packs == []


# ---------------------------------------------------------------------------
# Integration tests: orchestrator with real API packs
# ---------------------------------------------------------------------------


class TestOrchestratorManual:
    """Test orchestrator with manually added vendors."""

    def test_add_vendor(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        mock = orch.add_vendor("companies_house_lookup")
        assert mock.pack_name == "companies_house_lookup"
        assert mock.provider == "Companies House"
        assert mock.port == 19001
        assert mock.base_url == "http://127.0.0.1:19001"
        assert mock.env_var == "DAZZLE_API_COMPANIES_HOUSE_LOOKUP_URL"

    def test_add_multiple_vendors_sequential_ports(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        m1 = orch.add_vendor("companies_house_lookup")
        m2 = orch.add_vendor("stripe_payments")
        assert m1.port == 19001
        assert m2.port == 19002

    def test_add_vendor_explicit_port(self) -> None:
        orch = MockOrchestrator(seed=1)
        mock = orch.add_vendor("companies_house_lookup", port=18080)
        assert mock.port == 18080

    def test_add_duplicate_returns_existing(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        m1 = orch.add_vendor("companies_house_lookup")
        m2 = orch.add_vendor("companies_house_lookup")
        assert m1 is m2

    def test_add_unknown_pack_raises(self) -> None:
        orch = MockOrchestrator(seed=1)
        with pytest.raises(ValueError, match="not found"):
            orch.add_vendor("nonexistent_pack_xyz")

    def test_vendors_property(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("companies_house_lookup")
        orch.add_vendor("stripe_payments")
        vendors = orch.vendors
        assert "companies_house_lookup" in vendors
        assert "stripe_payments" in vendors
        assert len(vendors) == 2


class TestOrchestratorFromAppSpec:
    """Test auto-discovery from AppSpec."""

    def test_from_appspec_discovers_packs(self) -> None:
        appspec = _make_appspec(
            _make_api("companies_house", "pack:companies_house_lookup"),
            _make_api("stripe", "pack:stripe_payments"),
        )
        orch = MockOrchestrator.from_appspec(appspec, seed=1, base_port=19001)
        assert "companies_house_lookup" in orch.vendors
        assert "stripe_payments" in orch.vendors
        assert len(orch.vendors) == 2

    def test_from_appspec_empty(self) -> None:
        appspec = _make_appspec()
        orch = MockOrchestrator.from_appspec(appspec)
        assert len(orch.vendors) == 0


class TestOrchestratorEnvInjection:
    """Test environment variable injection and cleanup."""

    def test_inject_env(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("companies_house_lookup")
        injected = orch.inject_env()
        try:
            assert "DAZZLE_API_COMPANIES_HOUSE_LOOKUP_URL" in injected
            assert os.environ["DAZZLE_API_COMPANIES_HOUSE_LOOKUP_URL"] == "http://127.0.0.1:19001"
        finally:
            orch.clear_env()

    def test_clear_env(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("companies_house_lookup")
        orch.inject_env()
        orch.clear_env()
        assert "DAZZLE_API_COMPANIES_HOUSE_LOOKUP_URL" not in os.environ


class TestOrchestratorApps:
    """Test accessing mock apps and stores for test assertions."""

    def test_get_app(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("companies_house_lookup")
        app = orch.get_app("companies_house_lookup")
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "Companies House"

    def test_get_store(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("companies_house_lookup")
        store = orch.get_store("companies_house_lookup")
        assert store is not None

    def test_get_app_unknown_raises(self) -> None:
        orch = MockOrchestrator(seed=1)
        with pytest.raises(KeyError):
            orch.get_app("nonexistent")

    def test_health_check(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("companies_house_lookup")
        orch.add_vendor("stripe_payments")
        health = orch.health_check()
        assert health["companies_house_lookup"] is True
        assert health["stripe_payments"] is True

    def test_multi_vendor_crud(self) -> None:
        """Test CRUD operations across multiple vendor mocks."""
        orch = MockOrchestrator(seed=42, base_port=19001)
        orch.add_vendor("companies_house_lookup")
        orch.add_vendor("stripe_payments")

        companies_client = TestClient(
            orch.get_app("companies_house_lookup"), raise_server_exceptions=False
        )
        resp = companies_client.get(
            "/search/companies",
            params={"q": "acme"},
            headers={"Authorization": "Basic dGVzdDo="},
        )
        assert resp.status_code == 200

        stripe_client = TestClient(orch.get_app("stripe_payments"), raise_server_exceptions=False)
        resp = stripe_client.post(
            "/payment_intents",
            json={"amount": 5000, "currency": "gbp"},
            headers={"Authorization": "Bearer sk_test_123"},
        )
        assert resp.status_code == 201

        # State stores are isolated
        payment_intents = orch.get_store("stripe_payments").list("PaymentIntent")
        assert len(payment_intents) == 1
        assert orch.get_store("companies_house_lookup") is not orch.get_store("stripe_payments")


class TestOrchestratorLifecycle:
    """Test start/stop lifecycle."""

    def test_not_running_initially(self) -> None:
        orch = MockOrchestrator(seed=1)
        assert orch.is_running is False

    def test_stop_without_start_is_safe(self) -> None:
        orch = MockOrchestrator(seed=1)
        orch.stop()  # Should not raise
        assert orch.is_running is False
