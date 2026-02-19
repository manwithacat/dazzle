"""Tests for vendor mock orchestrator."""

from __future__ import annotations

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
        assert _pack_to_env_var("sumsub_kyc") == "DAZZLE_API_SUMSUB_KYC_URL"

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
            _make_api("sumsub", "pack:sumsub_kyc"),
        )
        packs = discover_packs_from_appspec(appspec)
        assert packs == ["stripe_payments", "sumsub_kyc"]

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
        mock = orch.add_vendor("sumsub_kyc")
        assert mock.pack_name == "sumsub_kyc"
        assert mock.provider == "SumSub"
        assert mock.port == 19001
        assert mock.base_url == "http://127.0.0.1:19001"
        assert mock.env_var == "DAZZLE_API_SUMSUB_KYC_URL"

    def test_add_multiple_vendors_sequential_ports(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        m1 = orch.add_vendor("sumsub_kyc")
        m2 = orch.add_vendor("stripe_payments")
        assert m1.port == 19001
        assert m2.port == 19002

    def test_add_vendor_explicit_port(self) -> None:
        orch = MockOrchestrator(seed=1)
        mock = orch.add_vendor("sumsub_kyc", port=18080)
        assert mock.port == 18080

    def test_add_duplicate_returns_existing(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        m1 = orch.add_vendor("sumsub_kyc")
        m2 = orch.add_vendor("sumsub_kyc")
        assert m1 is m2

    def test_add_unknown_pack_raises(self) -> None:
        orch = MockOrchestrator(seed=1)
        with pytest.raises(ValueError, match="not found"):
            orch.add_vendor("nonexistent_pack_xyz")

    def test_vendors_property(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("sumsub_kyc")
        orch.add_vendor("stripe_payments")
        vendors = orch.vendors
        assert "sumsub_kyc" in vendors
        assert "stripe_payments" in vendors
        assert len(vendors) == 2


class TestOrchestratorFromAppSpec:
    """Test auto-discovery from AppSpec."""

    def test_from_appspec_discovers_packs(self) -> None:
        appspec = _make_appspec(
            _make_api("sumsub", "pack:sumsub_kyc"),
            _make_api("stripe", "pack:stripe_payments"),
        )
        orch = MockOrchestrator.from_appspec(appspec, seed=1, base_port=19001)
        assert "sumsub_kyc" in orch.vendors
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
        orch.add_vendor("sumsub_kyc")
        injected = orch.inject_env()
        try:
            assert "DAZZLE_API_SUMSUB_KYC_URL" in injected
            assert os.environ["DAZZLE_API_SUMSUB_KYC_URL"] == "http://127.0.0.1:19001"
        finally:
            orch.clear_env()

    def test_clear_env(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("sumsub_kyc")
        orch.inject_env()
        orch.clear_env()
        assert "DAZZLE_API_SUMSUB_KYC_URL" not in os.environ


class TestOrchestratorApps:
    """Test accessing mock apps and stores for test assertions."""

    def test_get_app(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("sumsub_kyc")
        app = orch.get_app("sumsub_kyc")
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "SumSub"

    def test_get_store(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("sumsub_kyc")
        store = orch.get_store("sumsub_kyc")
        assert store is not None

    def test_get_app_unknown_raises(self) -> None:
        orch = MockOrchestrator(seed=1)
        with pytest.raises(KeyError):
            orch.get_app("nonexistent")

    def test_health_check(self) -> None:
        orch = MockOrchestrator(seed=1, base_port=19001)
        orch.add_vendor("sumsub_kyc")
        orch.add_vendor("stripe_payments")
        health = orch.health_check()
        assert health["sumsub_kyc"] is True
        assert health["stripe_payments"] is True

    def test_multi_vendor_crud(self) -> None:
        """Test CRUD operations across multiple vendor mocks."""
        orch = MockOrchestrator(seed=42, base_port=19001)
        orch.add_vendor("sumsub_kyc")
        orch.add_vendor("stripe_payments")

        # SumSub: create applicant
        sumsub_client = TestClient(orch.get_app("sumsub_kyc"), raise_server_exceptions=False)
        resp = sumsub_client.post(
            "/resources/applicants",
            json={"type": "individual", "email": "test@example.com"},
            headers={
                "X-App-Token": "tok",
                "X-App-Access-Ts": "123",
                "X-App-Access-Sig": "sig",
            },
        )
        assert resp.status_code == 201

        # Stripe: create payment intent
        stripe_client = TestClient(orch.get_app("stripe_payments"), raise_server_exceptions=False)
        resp = stripe_client.post(
            "/payment_intents",
            json={"amount": 5000, "currency": "gbp"},
            headers={"Authorization": "Bearer sk_test_123"},
        )
        assert resp.status_code == 201

        # State stores are isolated
        sumsub_records = orch.get_store("sumsub_kyc").list("Applicant")
        assert len(sumsub_records) == 1


class TestOrchestratorLifecycle:
    """Test start/stop lifecycle."""

    def test_not_running_initially(self) -> None:
        orch = MockOrchestrator(seed=1)
        assert orch.is_running is False

    def test_stop_without_start_is_safe(self) -> None:
        orch = MockOrchestrator(seed=1)
        orch.stop()  # Should not raise
        assert orch.is_running is False
