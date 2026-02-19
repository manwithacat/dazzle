"""Tests for vendor mock scenario engine."""

from __future__ import annotations

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
    def test_load_scenario(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenario = engine.load_scenario("sumsub_kyc", "kyc_approved")
        assert scenario.name == "kyc_approved"
        assert scenario.vendor == "sumsub_kyc"
        assert len(scenario.steps) > 0

    def test_load_scenario_not_found(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        with pytest.raises(FileNotFoundError, match="Scenario not found"):
            engine.load_scenario("sumsub_kyc", "nonexistent_scenario")

    def test_load_scenario_unknown_vendor(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        with pytest.raises(FileNotFoundError):
            engine.load_scenario("unknown_vendor", "anything")

    def test_scenario_steps_parsed(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenario = engine.load_scenario("sumsub_kyc", "kyc_rejected")
        # Should have steps for create_applicant, request_check, get_applicant_status, get_review_result
        ops = [s.operation for s in scenario.steps]
        assert "create_applicant" in ops
        assert "request_check" in ops
        assert "get_review_result" in ops

    def test_scenario_response_overrides(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenario = engine.load_scenario("sumsub_kyc", "kyc_rejected")
        review_step = next(s for s in scenario.steps if s.operation == "get_review_result")
        assert review_step.response_override["review_result"] == "RED"
        assert "DOCUMENT_FACE_MISMATCH" in review_step.response_override["reject_labels"]

    def test_scenario_status_override(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenario = engine.load_scenario("stripe_payments", "payment_failed_insufficient")
        confirm_step = next(s for s in scenario.steps if s.operation == "confirm_payment_intent")
        assert confirm_step.status_override == 402

    def test_scenario_delay(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenario = engine.load_scenario("sumsub_kyc", "kyc_rejected")
        check_step = next(s for s in scenario.steps if s.operation == "request_check")
        assert check_step.delay_ms == 500


class TestScenarioListing:
    def test_list_all_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios()
        assert len(scenarios) >= 19
        assert "sumsub_kyc/kyc_approved" in scenarios
        assert "stripe_payments/payment_succeeded" in scenarios

    def test_list_vendor_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="sumsub_kyc")
        assert len(scenarios) >= 4
        assert all(s.startswith("sumsub_kyc/") for s in scenarios)

    def test_list_unknown_vendor(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="nonexistent")
        assert scenarios == []

    def test_list_nonexistent_dir(self) -> None:
        engine = ScenarioEngine(scenarios_dir=Path("/nonexistent"))
        scenarios = engine.list_scenarios()
        assert scenarios == []


class TestScenarioReset:
    def test_reset_specific_vendor(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.load_scenario("sumsub_kyc", "kyc_approved")
        engine.load_scenario("stripe_payments", "payment_succeeded")
        assert len(engine.active_scenarios) == 2

        engine.reset(vendor="sumsub_kyc")
        assert "sumsub_kyc" not in engine.active_scenarios
        assert "stripe_payments" in engine.active_scenarios

    def test_reset_all(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.load_scenario("sumsub_kyc", "kyc_approved")
        engine.load_scenario("stripe_payments", "payment_succeeded")
        engine.reset()
        assert len(engine.active_scenarios) == 0

    def test_active_scenarios_property(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        assert engine.active_scenarios == {}
        engine.load_scenario("sumsub_kyc", "kyc_approved")
        assert engine.active_scenarios == {"sumsub_kyc": "kyc_approved"}


class TestScenarioIntercept:
    def test_intercept_with_override(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.load_scenario("sumsub_kyc", "kyc_rejected")

        data, status = _run_async(
            engine.intercept("sumsub_kyc", "get_review_result", {"id": "abc"}, 200)
        )
        assert data["review_result"] == "RED"
        assert "DOCUMENT_FACE_MISMATCH" in data["reject_labels"]
        assert data["id"] == "abc"  # Original data preserved
        assert status == 200  # No status override for this step

    def test_intercept_with_status_override(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.load_scenario("hmrc_mtd_vat", "vat_return_rejected")

        data, status = _run_async(
            engine.intercept("hmrc_mtd_vat", "submit_return", {"id": "ret-1"}, 201)
        )
        assert status == 422
        assert data["code"] == "INVALID_REQUEST"

    def test_intercept_no_match(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        engine.load_scenario("sumsub_kyc", "kyc_approved")

        # Operation not in scenario steps
        data, status = _run_async(
            engine.intercept("sumsub_kyc", "delete_applicant", {"ok": True}, 200)
        )
        assert data == {"ok": True}
        assert status == 200

    def test_intercept_no_active_scenario(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)

        data, status = _run_async(
            engine.intercept("sumsub_kyc", "create_applicant", {"id": "abc"}, 201)
        )
        assert data == {"id": "abc"}
        assert status == 201


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

    def test_all_scenarios_loadable(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        all_scenarios = engine.list_scenarios()
        assert len(all_scenarios) >= 19

        for scenario_ref in all_scenarios:
            vendor, name = scenario_ref.split("/", 1)
            scenario = engine.load_scenario(vendor, name)
            assert scenario.name == name
            assert scenario.vendor == vendor
            assert len(scenario.steps) > 0, f"Scenario {scenario_ref} has no steps"

    def test_sumsub_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="sumsub_kyc")
        assert len(scenarios) >= 4
        names = {s.split("/")[1] for s in scenarios}
        assert "kyc_approved" in names
        assert "kyc_rejected" in names

    def test_stripe_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="stripe_payments")
        assert len(scenarios) >= 3
        names = {s.split("/")[1] for s in scenarios}
        assert "payment_succeeded" in names
        assert "payment_failed_insufficient" in names

    def test_hmrc_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="hmrc_mtd_vat")
        assert len(scenarios) >= 3

    def test_xero_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="xero_accounting")
        assert len(scenarios) >= 3

    def test_docuseal_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="docuseal_signatures")
        assert len(scenarios) >= 3

    def test_companies_house_scenarios(self) -> None:
        engine = ScenarioEngine(scenarios_dir=SCENARIOS_DIR)
        scenarios = engine.list_scenarios(vendor="companies_house_lookup")
        assert len(scenarios) >= 3
