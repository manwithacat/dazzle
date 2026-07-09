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
        s = engine.load_scenario("sumsub_kyc", "kyc_approved")
        assert s.name == "kyc_approved"
        assert s.vendor == "sumsub_kyc"
        assert len(s.steps) > 0

        # Not found
        with pytest.raises(FileNotFoundError, match="Scenario not found"):
            engine.load_scenario("sumsub_kyc", "nonexistent_scenario")

        # Unknown vendor
        with pytest.raises(FileNotFoundError):
            engine.load_scenario("unknown_vendor", "anything")

        # Steps parsed
        rej = engine.load_scenario("sumsub_kyc", "kyc_rejected")
        ops = [step.operation for step in rej.steps]
        assert "create_applicant" in ops
        assert "request_check" in ops
        assert "get_review_result" in ops

        # Response overrides
        review_step = next(step for step in rej.steps if step.operation == "get_review_result")
        assert review_step.response_override["review_result"] == "RED"
        assert "DOCUMENT_FACE_MISMATCH" in review_step.response_override["reject_labels"]

        # Status override
        stripe = engine.load_scenario("stripe_payments", "payment_failed_insufficient")
        confirm_step = next(
            step for step in stripe.steps if step.operation == "confirm_payment_intent"
        )
        assert confirm_step.status_override == 402

        # Delay
        check_step = next(step for step in rej.steps if step.operation == "request_check")
        assert check_step.delay_ms == 500


class TestScenarioListing:
    def test_listing_combined(self) -> None:
        """Combined: list all, vendor filter, unknown vendor (empty),
        nonexistent dir (empty)."""
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)

        all_scenarios = engine.list_scenarios()
        assert len(all_scenarios) >= 16
        assert "sumsub_kyc/kyc_approved" in all_scenarios
        assert "stripe_payments/payment_succeeded" in all_scenarios

        sumsub = engine.list_scenarios(vendor="sumsub_kyc")
        assert len(sumsub) >= 4
        assert all(s.startswith("sumsub_kyc/") for s in sumsub)

        assert engine.list_scenarios(vendor="nonexistent") == []

        assert ScenarioEngine(scenarios_dir=Path("/nonexistent")).list_scenarios() == []


class TestScenarioReset:
    def test_reset_combined(self) -> None:
        """Combined: reset specific vendor, reset all, active_scenarios property."""
        # Reset specific
        e1 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e1.load_scenario("sumsub_kyc", "kyc_approved")
        e1.load_scenario("stripe_payments", "payment_succeeded")
        assert len(e1.active_scenarios) == 2
        e1.reset(vendor="sumsub_kyc")
        assert "sumsub_kyc" not in e1.active_scenarios
        assert "stripe_payments" in e1.active_scenarios

        # Reset all
        e2 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e2.load_scenario("sumsub_kyc", "kyc_approved")
        e2.load_scenario("stripe_payments", "payment_succeeded")
        e2.reset()
        assert len(e2.active_scenarios) == 0

        # active_scenarios property
        e3 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        assert e3.active_scenarios == {}
        e3.load_scenario("sumsub_kyc", "kyc_approved")
        assert e3.active_scenarios == {"sumsub_kyc": "kyc_approved"}


class TestScenarioIntercept:
    def test_intercept_combined(self) -> None:
        """Combined: intercept with override, with status_override, no match,
        no active scenario."""
        # With override
        e1 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e1.load_scenario("sumsub_kyc", "kyc_rejected")
        data, status = _run_async(
            e1.intercept("sumsub_kyc", "get_review_result", {"id": "abc"}, 200)
        )
        assert data["review_result"] == "RED"
        assert "DOCUMENT_FACE_MISMATCH" in data["reject_labels"]
        assert data["id"] == "abc"
        assert status == 200

        # With status override
        e2 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e2.load_scenario("hmrc_mtd_vat", "vat_return_rejected")
        data2, status2 = _run_async(
            e2.intercept("hmrc_mtd_vat", "submit_return", {"id": "ret-1"}, 201)
        )
        assert status2 == 422
        assert data2["code"] == "INVALID_REQUEST"

        # No match
        e3 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        e3.load_scenario("sumsub_kyc", "kyc_approved")
        data3, status3 = _run_async(
            e3.intercept("sumsub_kyc", "delete_applicant", {"ok": True}, 200)
        )
        assert data3 == {"ok": True}
        assert status3 == 200

        # No active scenario
        e4 = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        data4, status4 = _run_async(
            e4.intercept("sumsub_kyc", "create_applicant", {"id": "abc"}, 201)
        )
        assert data4 == {"id": "abc"}
        assert status4 == 201


class TestErrorInjection:
    def test_inject_error_immediate(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_error("sumsub_kyc", "create_applicant", status=500)

        data, status = _run_async(
            engine.intercept("sumsub_kyc", "create_applicant", {"id": "abc"}, 201)
        )
        assert status == 500
        assert "error" in data

    def test_inject_error_after_n(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_error("sumsub_kyc", "create_applicant", status=503, after_n=2)

        # First two calls succeed (index 0 and 1)
        data1, status1 = _run_async(
            engine.intercept("sumsub_kyc", "create_applicant", {"id": "1"}, 201)
        )
        assert status1 == 201

        data2, status2 = _run_async(
            engine.intercept("sumsub_kyc", "create_applicant", {"id": "2"}, 201)
        )
        assert status2 == 201

        # Third call fails (index 2 >= after_n)
        data3, status3 = _run_async(
            engine.intercept("sumsub_kyc", "create_applicant", {"id": "3"}, 201)
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
        engine.inject_latency("hmrc_mtd_vat", "submit_return", delay_ms=50)

        start = time.monotonic()
        _run_async(engine.intercept("hmrc_mtd_vat", "submit_return", {"ok": True}, 200))
        elapsed = (time.monotonic() - start) * 1000
        assert elapsed >= 40  # At least ~40ms (allowing for timing variance)

    def test_reset_clears_injections(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.inject_error("sumsub_kyc", "create_applicant", status=500)
        engine.inject_latency("sumsub_kyc", "get_applicant", delay_ms=100)

        engine.reset(vendor="sumsub_kyc")

        data, status = _run_async(
            engine.intercept("sumsub_kyc", "create_applicant", {"id": "abc"}, 201)
        )
        assert status == 201  # No error injection

    def test_error_takes_precedence_over_scenario(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.load_scenario("sumsub_kyc", "kyc_approved")
        engine.inject_error("sumsub_kyc", "create_applicant", status=500)

        data, status = _run_async(
            engine.intercept("sumsub_kyc", "create_applicant", {"id": "abc"}, 201)
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

    def test_kyc_approved_flow(self) -> None:
        client, engine = self._make_client("sumsub_kyc", "kyc_approved")
        auth = {"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"}

        # Create applicant
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["review_status"] == "init"
        applicant_id = data["id"]

        # Get review result
        resp = client.get(f"/resources/applicants/{applicant_id}", headers=auth)
        assert resp.status_code == 200

    def test_kyc_rejected_flow(self) -> None:
        client, engine = self._make_client("sumsub_kyc", "kyc_rejected")
        auth = {"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"}

        # Create applicant
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert resp.status_code == 201
        assert resp.json()["review_status"] == "init"

    def test_hmrc_rate_limited(self) -> None:
        client, engine = self._make_client("hmrc_mtd_vat", "rate_limited")
        auth = {"Authorization": "Bearer test-token"}

        resp = client.post(
            "/organisations/vat/{vrn}/returns",
            json={"periodKey": "A001"},
            headers=auth,
        )
        assert resp.status_code == 429
        assert resp.json()["code"] == "TOO_MANY_REQUESTS"

    def test_error_injection_with_server(self) -> None:
        client, engine = self._make_client("sumsub_kyc")
        auth = {"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"}

        # No error initially
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert resp.status_code == 201

        # Inject error
        engine.inject_error("sumsub_kyc", "create_applicant", status=503)
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert resp.status_code == 503

        # Reset and verify normal operation
        engine.reset()
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert resp.status_code == 201

    def test_scenario_switch(self) -> None:
        client, engine = self._make_client("sumsub_kyc", "kyc_approved")
        auth = {"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"}

        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert resp.json()["review_status"] == "init"

        # Switch to rejected scenario
        engine.load_scenario("sumsub_kyc", "kyc_rejected")
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert resp.json()["review_status"] == "init"  # Same for create step

    def test_recorder_works_with_scenarios(self) -> None:
        client, engine = self._make_client("sumsub_kyc", "kyc_approved")
        recorder = get_recorder(client.app)
        auth = {"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"}

        client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth,
        )
        assert recorder.request_count == 1
        recorder.assert_called(method="POST", path="/resources/applicants")


# ---------------------------------------------------------------------------
# Built-in scenario TOML validation
# ---------------------------------------------------------------------------


class TestBuiltInScenarios:
    """Verify all built-in scenario TOML files are valid."""

    def test_built_in_scenarios_combined(self) -> None:
        """Combined: all scenarios loadable + per-vendor coverage
        (sumsub, stripe, hmrc, xero, companies_house)."""
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)

        all_scenarios = engine.list_scenarios()
        assert len(all_scenarios) >= 16

        for scenario_ref in all_scenarios:
            vendor, name = scenario_ref.split("/", 1)
            scenario = engine.load_scenario(vendor, name)
            assert scenario.name == name
            assert scenario.vendor == vendor
            assert len(scenario.steps) > 0, f"Scenario {scenario_ref} has no steps"

        # Sumsub
        sumsub = engine.list_scenarios(vendor="sumsub_kyc")
        assert len(sumsub) >= 4
        sumsub_names = {s.split("/")[1] for s in sumsub}
        assert "kyc_approved" in sumsub_names
        assert "kyc_rejected" in sumsub_names

        # Stripe
        stripe = engine.list_scenarios(vendor="stripe_payments")
        assert len(stripe) >= 3
        stripe_names = {s.split("/")[1] for s in stripe}
        assert "payment_succeeded" in stripe_names
        assert "payment_failed_insufficient" in stripe_names

        # HMRC, Xero, Companies House
        assert len(engine.list_scenarios(vendor="hmrc_mtd_vat")) >= 3
        assert len(engine.list_scenarios(vendor="xero_accounting")) >= 3
        assert len(engine.list_scenarios(vendor="companies_house_lookup")) >= 3
