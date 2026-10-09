"""Tests for vendor mock scenario engine."""

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dazzle.testing.vendor_mock.assertions import get_recorder
from dazzle.testing.vendor_mock.generator import create_mock_server
from dazzle.testing.vendor_mock.scenarios import ScenarioEngine

# The built-in scenarios directory
SCENARIOS_DIR = (
    Path(__file__).parent.parent.parent / "src" / "dazzle" / "testing" / "vendor_mock" / "scenarios"
)


def _run_async(coro: Any) -> Any:
    """Run an async function synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# ScenarioEngine unit tests
# ---------------------------------------------------------------------------


class TestScenarioLoading:
    def test_loading_combined(self) -> None:
        """Combined: load_scenario, not-found, unknown vendor, steps parsed,
        response_overrides, status_override, delay."""
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)

        # Load scenario
        s = engine.load_scenario("stripe_payments", "payment_succeeded")
        assert s.name == "payment_succeeded"
        assert s.vendor == "stripe_payments"
        assert len(s.steps) > 0

        # Not found
        with pytest.raises(FileNotFoundError, match="Scenario not found"):
            engine.load_scenario("stripe_payments", "nonexistent_scenario")

        # Unknown vendor
        with pytest.raises(FileNotFoundError):
            engine.load_scenario("unknown_vendor", "anything")

        # Steps parsed
        failed = engine.load_scenario("stripe_payments", "payment_failed_insufficient")
        ops = [step.operation for step in failed.steps]
        assert "create_payment_intent" in ops
        assert "confirm_payment_intent" in ops

        # Response overrides
        create_step = next(step for step in s.steps if step.operation == "create_payment_intent")
        assert create_step.response_override["status"] == "requires_confirmation"

        # Status override
        confirm_step = next(
            step for step in failed.steps if step.operation == "confirm_payment_intent"
        )
        assert confirm_step.status_override == 402
        assert confirm_step.response_override["last_payment_error"]["decline_code"] == (
            "insufficient_funds"
        )


class TestScenarioListing:
    def test_listing_combined(self) -> None:
        """Combined: list all, vendor filter, unknown vendor (empty),
        nonexistent dir (empty)."""
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)

        all_scenarios = engine.list_scenarios()
        assert len(all_scenarios) >= 7
        assert "stripe_payments/payment_succeeded" in all_scenarios
        assert "companies_house_lookup/company_found" in all_scenarios
        assert engine.list_scenarios(vendor="sumsub_kyc") == []

        stripe = engine.list_scenarios(vendor="stripe_payments")
        assert len(stripe) >= 4
        assert all(s.startswith("stripe_payments/") for s in stripe)

        assert engine.list_scenarios(vendor="nonexistent") == []

        assert ScenarioEngine(scenarios_dir=Path("/nonexistent")).list_scenarios() == []


class TestScenarioReset:
    def test_reset_combined(self) -> None:
        """Combined: reset specific vendor, reset all, active_scenarios property."""
        # Reset specific
        e1 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e1.load_scenario("companies_house_lookup", "company_found")
        e1.load_scenario("stripe_payments", "payment_succeeded")
        assert len(e1.active_scenarios) == 2
        e1.reset(vendor="companies_house_lookup")
        assert "companies_house_lookup" not in e1.active_scenarios
        assert "stripe_payments" in e1.active_scenarios

        # Reset all
        e2 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e2.load_scenario("companies_house_lookup", "company_found")
        e2.load_scenario("stripe_payments", "payment_succeeded")
        e2.reset()
        assert len(e2.active_scenarios) == 0

        # active_scenarios property
        e3 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        assert e3.active_scenarios == {}
        e3.load_scenario("stripe_payments", "payment_succeeded")
        assert e3.active_scenarios == {"stripe_payments": "payment_succeeded"}


class TestScenarioIntercept:
    def test_intercept_combined(self) -> None:
        """Combined: intercept with override, with status_override, no match,
        no active scenario."""
        # With override
        e1 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e1.load_scenario("stripe_payments", "payment_succeeded")
        data, status = _run_async(
            e1.intercept("stripe_payments", "create_payment_intent", {"id": "pi_1"}, 200)
        )
        assert data["status"] == "requires_confirmation"
        assert data["id"] == "pi_1"
        assert status == 200

        # With status override
        e2 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e2.load_scenario("stripe_payments", "payment_failed_insufficient")
        data2, status2 = _run_async(
            e2.intercept("stripe_payments", "confirm_payment_intent", {"id": "pi_1"}, 200)
        )
        assert status2 == 402
        assert data2["last_payment_error"]["decline_code"] == "insufficient_funds"
        assert data2["id"] == "pi_1"

        # No match
        e3 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e3.load_scenario("stripe_payments", "payment_succeeded")
        data3, status3 = _run_async(
            e3.intercept("stripe_payments", "create_refund", {"ok": True}, 200)
        )
        assert data3 == {"ok": True}
        assert status3 == 200

        # No active scenario
        e4 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        data4, status4 = _run_async(
            e4.intercept("stripe_payments", "create_payment_intent", {"id": "abc"}, 201)
        )
        assert data4 == {"id": "abc"}
        assert status4 == 201


class TestErrorInjection:
    def test_inject_error_immediate(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_error("stripe_payments", "create_payment_intent", status=500)

        data, status = _run_async(
            engine.intercept("stripe_payments", "create_payment_intent", {"id": "abc"}, 201)
        )
        assert status == 500
        assert "error" in data

    def test_inject_error_after_n(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_error("stripe_payments", "create_payment_intent", status=503, after_n=2)

        # First two calls succeed (index 0 and 1)
        data1, status1 = _run_async(
            engine.intercept("stripe_payments", "create_payment_intent", {"id": "1"}, 201)
        )
        assert status1 == 201

        data2, status2 = _run_async(
            engine.intercept("stripe_payments", "create_payment_intent", {"id": "2"}, 201)
        )
        assert status2 == 201

        # Third call fails (index 2 >= after_n)
        data3, status3 = _run_async(
            engine.intercept("stripe_payments", "create_payment_intent", {"id": "3"}, 201)
        )
        assert status3 == 503

    def test_inject_error_custom_body(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_error(
            "stripe_payments",
            "create_payment_intent",
            status=429,
            body={"error": "rate_limited", "retry_after": 60},
        )

        data, status = _run_async(
            engine.intercept("stripe_payments", "create_payment_intent", {}, 201)
        )
        assert status == 429
        assert data["retry_after"] == 60

    def test_inject_latency(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_latency("stripe_payments", "create_payment_intent", delay_ms=50)

        start = time.monotonic()
        _run_async(engine.intercept("stripe_payments", "create_payment_intent", {"ok": True}, 200))
        elapsed = (time.monotonic() - start) * 1000
        assert elapsed >= 40  # At least ~40ms (allowing for timing variance)

    def test_reset_clears_injections(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_error("stripe_payments", "create_payment_intent", status=500)
        engine.inject_latency("stripe_payments", "get_payment_intent", delay_ms=100)

        engine.reset(vendor="stripe_payments")

        data, status = _run_async(
            engine.intercept("stripe_payments", "create_payment_intent", {"id": "abc"}, 201)
        )
        assert status == 201  # No error injection

    def test_error_takes_precedence_over_scenario(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.load_scenario("stripe_payments", "payment_succeeded")
        engine.inject_error("stripe_payments", "create_payment_intent", status=500)

        data, status = _run_async(
            engine.intercept("stripe_payments", "create_payment_intent", {"id": "abc"}, 201)
        )
        # Error injection takes precedence
        assert status == 500


# ---------------------------------------------------------------------------
# Integration: scenario engine with live mock server
# ---------------------------------------------------------------------------


class TestScenarioWithMockServer:
    def _make_client(
        self, vendor: str, scenario: str | None = None
    ) -> tuple[TestClient, ScenarioEngine]:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        if scenario:
            engine.load_scenario(vendor, scenario)
        app = create_mock_server(vendor, seed=42, scenario_engine=engine)
        client = TestClient(app, raise_server_exceptions=False)
        return client, engine

    def test_payment_succeeded_flow(self) -> None:
        client, engine = self._make_client("stripe_payments", "payment_succeeded")
        auth = {"Authorization": "Bearer test-token"}

        resp = client.post(
            "/payment_intents",
            json={"amount": 100, "currency": "gbp"},
            headers=auth,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "requires_confirmation"
        payment_id = data["id"]

        resp = client.get(f"/payment_intents/{payment_id}", headers=auth)
        assert resp.status_code == 200

    def test_payment_failed_flow(self) -> None:
        client, engine = self._make_client("stripe_payments", "payment_failed_insufficient")
        auth = {"Authorization": "Bearer test-token"}

        resp = client.post(
            "/payment_intents",
            json={"amount": 100, "currency": "gbp"},
            headers=auth,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "requires_confirmation"

    def test_stripe_rate_limited(self) -> None:
        client, engine = self._make_client("stripe_payments", "rate_limited")
        auth = {"Authorization": "Bearer test-token"}

        resp = client.post(
            "/payment_intents",
            json={"amount": 100, "currency": "gbp"},
            headers=auth,
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "rate_limit"

    def test_error_injection_with_server(self) -> None:
        client, engine = self._make_client("stripe_payments")
        auth = {"Authorization": "Bearer test-token"}
        body = {"amount": 100, "currency": "gbp"}

        resp = client.post("/payment_intents", json=body, headers=auth)
        assert resp.status_code == 201

        engine.inject_error("stripe_payments", "create_payment_intent", status=503)
        resp = client.post("/payment_intents", json=body, headers=auth)
        assert resp.status_code == 503

        engine.reset()
        resp = client.post("/payment_intents", json=body, headers=auth)
        assert resp.status_code == 201

    def test_scenario_switch(self) -> None:
        client, engine = self._make_client("stripe_payments", "payment_succeeded")
        auth = {"Authorization": "Bearer test-token"}
        body = {"amount": 100, "currency": "gbp"}

        resp = client.post("/payment_intents", json=body, headers=auth)
        assert resp.json()["status"] == "requires_confirmation"

        engine.load_scenario("stripe_payments", "rate_limited")
        resp = client.post("/payment_intents", json=body, headers=auth)
        assert resp.status_code == 429

    def test_recorder_works_with_scenarios(self) -> None:
        client, engine = self._make_client("stripe_payments", "payment_succeeded")
        recorder = get_recorder(client.app)
        auth = {"Authorization": "Bearer test-token"}

        client.post(
            "/payment_intents",
            json={"amount": 100, "currency": "gbp"},
            headers=auth,
        )
        assert recorder.request_count == 1
        recorder.assert_called(method="POST", path="/payment_intents")


# ---------------------------------------------------------------------------
# Built-in scenario TOML validation
# ---------------------------------------------------------------------------


class TestBuiltInScenarios:
    """Verify all built-in scenario TOML files are valid."""

    def test_built_in_scenarios_combined(self) -> None:
        """Combined: all scenarios loadable + per-vendor coverage
        (stripe, companies_house)."""
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)

        all_scenarios = engine.list_scenarios()
        assert len(all_scenarios) >= 7

        for scenario_ref in all_scenarios:
            vendor, name = scenario_ref.split("/", 1)
            scenario = engine.load_scenario(vendor, name)
            assert scenario.name == name
            assert scenario.vendor == vendor
            assert len(scenario.steps) > 0, f"Scenario {scenario_ref} has no steps"

        # Stripe
        stripe = engine.list_scenarios(vendor="stripe_payments")
        assert len(stripe) >= 4
        stripe_names = {s.split("/")[1] for s in stripe}
        assert "payment_succeeded" in stripe_names
        assert "payment_failed_insufficient" in stripe_names

        # Companies House. HMRC, Xero, and SumSub are not built-in vendors.
        assert engine.list_scenarios(vendor="hmrc_mtd_vat") == []
        assert engine.list_scenarios(vendor="xero_accounting") == []
        assert engine.list_scenarios(vendor="sumsub_kyc") == []
        assert len(engine.list_scenarios(vendor="companies_house_lookup")) >= 3
