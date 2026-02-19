"""Tests for vendor mock pytest fixtures and assertion helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dazzle.core.ir.services import APISpec, AuthProfile
from dazzle.testing.vendor_mock.assertions import RequestRecorder, get_recorder
from dazzle.testing.vendor_mock.fixtures import mock_vendor
from dazzle.testing.vendor_mock.orchestrator import MockOrchestrator

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
# RequestRecorder tests
# ---------------------------------------------------------------------------


class TestRequestRecorder:
    """Test RequestRecorder assertion helpers."""

    def _make_log(self) -> list[dict[str, Any]]:
        return [
            {
                "operation": "create_applicant",
                "method": "POST",
                "path": "/resources/applicants",
                "query": {},
                "body": {"type": "individual", "email": "test@example.com"},
                "timestamp": 1000.0,
                "status": 201,
                "elapsed_ms": 1.5,
            },
            {
                "operation": "get_applicant",
                "method": "GET",
                "path": "/resources/applicants/abc-123",
                "query": {},
                "body": None,
                "timestamp": 1001.0,
                "status": 200,
                "elapsed_ms": 0.5,
            },
        ]

    def test_request_count(self) -> None:
        recorder = RequestRecorder(self._make_log())
        assert recorder.request_count == 2

    def test_requests_returns_copy(self) -> None:
        log = self._make_log()
        recorder = RequestRecorder(log)
        requests = recorder.requests
        assert len(requests) == 2
        requests.clear()
        assert recorder.request_count == 2  # Original unchanged

    def test_last_request(self) -> None:
        recorder = RequestRecorder(self._make_log())
        last = recorder.last_request
        assert last is not None
        assert last["operation"] == "get_applicant"

    def test_last_request_empty(self) -> None:
        recorder = RequestRecorder([])
        assert recorder.last_request is None

    def test_filter_by_method(self) -> None:
        recorder = RequestRecorder(self._make_log())
        posts = recorder.filter(method="POST")
        assert len(posts) == 1
        assert posts[0]["operation"] == "create_applicant"

    def test_filter_by_path(self) -> None:
        recorder = RequestRecorder(self._make_log())
        matches = recorder.filter(path="/resources/applicants/abc")
        assert len(matches) == 1
        assert matches[0]["method"] == "GET"

    def test_filter_by_status(self) -> None:
        recorder = RequestRecorder(self._make_log())
        created = recorder.filter(status=201)
        assert len(created) == 1

    def test_filter_by_operation(self) -> None:
        recorder = RequestRecorder(self._make_log())
        matches = recorder.filter(operation="create_applicant")
        assert len(matches) == 1

    def test_filter_combined(self) -> None:
        recorder = RequestRecorder(self._make_log())
        matches = recorder.filter(method="POST", status=201)
        assert len(matches) == 1
        matches = recorder.filter(method="GET", status=201)
        assert len(matches) == 0

    def test_assert_called_passes(self) -> None:
        recorder = RequestRecorder(self._make_log())
        recorder.assert_called(method="POST", path="/resources/applicants")

    def test_assert_called_with_times(self) -> None:
        recorder = RequestRecorder(self._make_log())
        recorder.assert_called(method="POST", path="/resources/applicants", times=1)

    def test_assert_called_fails(self) -> None:
        recorder = RequestRecorder(self._make_log())
        with pytest.raises(AssertionError, match="Expected at least one DELETE"):
            recorder.assert_called(method="DELETE", path="/resources")

    def test_assert_called_wrong_times(self) -> None:
        recorder = RequestRecorder(self._make_log())
        with pytest.raises(AssertionError, match="Expected 3"):
            recorder.assert_called(method="POST", path="/resources/applicants", times=3)

    def test_assert_not_called_passes(self) -> None:
        recorder = RequestRecorder(self._make_log())
        recorder.assert_not_called(method="DELETE", path="/anything")

    def test_assert_not_called_fails(self) -> None:
        recorder = RequestRecorder(self._make_log())
        with pytest.raises(AssertionError, match="Expected no POST"):
            recorder.assert_not_called(method="POST", path="/resources/applicants")

    def test_assert_body_contains_key(self) -> None:
        log = self._make_log()
        # Make the POST the last request
        recorder = RequestRecorder([log[0]])
        recorder.assert_body_contains("type")

    def test_assert_body_contains_key_value(self) -> None:
        log = self._make_log()
        recorder = RequestRecorder([log[0]])
        recorder.assert_body_contains("type", "individual")

    def test_assert_body_contains_wrong_value(self) -> None:
        log = self._make_log()
        recorder = RequestRecorder([log[0]])
        with pytest.raises(AssertionError, match="Expected body"):
            recorder.assert_body_contains("type", "corporate")

    def test_assert_body_contains_missing_key(self) -> None:
        log = self._make_log()
        recorder = RequestRecorder([log[0]])
        with pytest.raises(AssertionError, match="Key 'missing' not found"):
            recorder.assert_body_contains("missing")

    def test_assert_body_contains_no_requests(self) -> None:
        recorder = RequestRecorder([])
        with pytest.raises(AssertionError, match="No requests recorded"):
            recorder.assert_body_contains("key")

    def test_clear(self) -> None:
        recorder = RequestRecorder(self._make_log())
        assert recorder.request_count == 2
        recorder.clear()
        assert recorder.request_count == 0


# ---------------------------------------------------------------------------
# get_recorder tests
# ---------------------------------------------------------------------------


class TestGetRecorder:
    def test_from_mock_app(self) -> None:
        client = mock_vendor("sumsub_kyc")
        # The test client wraps a real FastAPI app
        recorder = get_recorder(client.app)
        assert recorder.request_count == 0

        # Make a request and verify it's recorded
        client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers={
                "X-App-Token": "tok",
                "X-App-Access-Ts": "0",
                "X-App-Access-Sig": "sig",
            },
        )
        assert recorder.request_count == 1
        recorder.assert_called(method="POST", path="/resources/applicants")


# ---------------------------------------------------------------------------
# mock_vendor helper tests
# ---------------------------------------------------------------------------


class TestMockVendor:
    def test_returns_test_client(self) -> None:
        client = mock_vendor("sumsub_kyc")
        assert isinstance(client, TestClient)

    def test_health_endpoint(self) -> None:
        client = mock_vendor("sumsub_kyc")
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "SumSub"

    def test_deterministic_seed(self) -> None:
        c1 = mock_vendor("sumsub_kyc", seed=42)
        c2 = mock_vendor("sumsub_kyc", seed=42)

        # Same seed → same generated IDs
        r1 = c1.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers={"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"},
        )
        r2 = c2.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers={"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"},
        )
        assert r1.json()["id"] == r2.json()["id"]

    def test_different_seed_different_generated_data(self) -> None:
        """Different seeds produce different generated field values."""
        from dazzle.testing.vendor_mock.data_generators import DataGenerator

        fields = {"name": {"type": "string"}, "email": {"type": "string"}}
        g1 = DataGenerator(seed=1)
        g2 = DataGenerator(seed=999)

        m1 = g1.generate_model("Test", fields)
        m2 = g2.generate_model("Test", fields)
        assert m1["name"] != m2["name"] or m1["email"] != m2["email"]

    def test_auth_token_validation(self) -> None:
        """HMAC auth accepts requests when no secret is provided for validation."""
        client = mock_vendor("sumsub_kyc")
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers={
                "X-App-Token": "any-token",
                "X-App-Access-Ts": "0",
                "X-App-Access-Sig": "any-sig",
            },
        )
        # No auth_tokens → any correctly-formatted auth accepted
        assert resp.status_code == 201

    def test_auth_missing_headers_rejected(self) -> None:
        """HMAC auth rejects requests without required headers."""
        client = mock_vendor("sumsub_kyc")
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual"},
        )
        assert resp.status_code == 401

    def test_unknown_pack_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            mock_vendor("nonexistent_pack_xyz")


# ---------------------------------------------------------------------------
# vendor_mocks fixture tests (test the fixture function directly)
# ---------------------------------------------------------------------------


class TestVendorMocksFixture:
    def test_fixture_lifecycle(self) -> None:
        """Test the orchestrator lifecycle: add, inject, clear."""
        import os

        orch = MockOrchestrator(seed=42, base_port=19001)
        orch.add_vendor("sumsub_kyc")
        orch.inject_env()
        assert "DAZZLE_API_SUMSUB_KYC_URL" in os.environ

        orch.clear_env()
        assert "DAZZLE_API_SUMSUB_KYC_URL" not in os.environ

    def test_orchestrator_seed_propagates(self) -> None:
        """Orchestrator seed produces deterministic mock data."""
        orch1 = MockOrchestrator(seed=42, base_port=19001)
        orch2 = MockOrchestrator(seed=42, base_port=19002)
        orch1.add_vendor("sumsub_kyc")
        orch2.add_vendor("sumsub_kyc")

        c1 = TestClient(orch1.get_app("sumsub_kyc"), raise_server_exceptions=False)
        c2 = TestClient(orch2.get_app("sumsub_kyc"), raise_server_exceptions=False)
        auth = {"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"}

        r1 = c1.post("/resources/applicants", json={"type": "individual"}, headers=auth)
        r2 = c2.post("/resources/applicants", json={"type": "individual"}, headers=auth)
        assert r1.json()["id"] == r2.json()["id"]


class TestVendorMocksFromAppspec:
    def test_from_appspec_auto_discovers(self) -> None:
        """MockOrchestrator.from_appspec discovers and registers vendors."""
        import os

        appspec = _make_appspec(_make_api("sumsub", "pack:sumsub_kyc"))
        orch = MockOrchestrator.from_appspec(appspec, seed=42, base_port=19001)
        assert "sumsub_kyc" in orch.vendors

        orch.inject_env()
        assert "DAZZLE_API_SUMSUB_KYC_URL" in os.environ
        orch.clear_env()
        assert "DAZZLE_API_SUMSUB_KYC_URL" not in os.environ

    def test_from_appspec_empty(self) -> None:
        """Empty appspec yields empty orchestrator."""
        appspec = _make_appspec()
        orch = MockOrchestrator.from_appspec(appspec)
        assert len(orch.vendors) == 0


# ---------------------------------------------------------------------------
# Integration: recorder with live mock
# ---------------------------------------------------------------------------


class TestRecorderIntegration:
    """End-to-end test: mock_vendor + recorder + assertions."""

    def test_full_crud_recording(self) -> None:
        client = mock_vendor("sumsub_kyc")
        recorder = get_recorder(client.app)
        auth_headers = {
            "X-App-Token": "tok",
            "X-App-Access-Ts": "0",
            "X-App-Access-Sig": "sig",
        }

        # Create
        resp = client.post(
            "/resources/applicants",
            json={"type": "individual", "email": "test@example.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        applicant_id = resp.json()["id"]

        # Read
        resp = client.get(f"/resources/applicants/{applicant_id}", headers=auth_headers)
        assert resp.status_code == 200

        # Verify recordings
        assert recorder.request_count == 2
        recorder.assert_called(method="POST", path="/resources/applicants", times=1)
        recorder.assert_called(method="GET", path="/resources/applicants", times=1)
        recorder.assert_not_called(method="DELETE", path="/resources/applicants")

    def test_filter_by_status_code(self) -> None:
        client = mock_vendor("sumsub_kyc")
        recorder = get_recorder(client.app)
        auth_headers = {
            "X-App-Token": "tok",
            "X-App-Access-Ts": "0",
            "X-App-Access-Sig": "sig",
        }

        # Successful create
        client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth_headers,
        )

        # Failed read (not found)
        client.get("/resources/applicants/nonexistent", headers=auth_headers)

        created = recorder.filter(status=201)
        assert len(created) == 1
        not_found = recorder.filter(status=404)
        assert len(not_found) == 1

    def test_clear_and_rerecord(self) -> None:
        client = mock_vendor("sumsub_kyc")
        recorder = get_recorder(client.app)
        auth_headers = {
            "X-App-Token": "tok",
            "X-App-Access-Ts": "0",
            "X-App-Access-Sig": "sig",
        }

        client.post(
            "/resources/applicants",
            json={"type": "individual"},
            headers=auth_headers,
        )
        assert recorder.request_count == 1

        recorder.clear()
        assert recorder.request_count == 0

        # Make another recorded request (health endpoint is unlogged)
        client.get("/resources/applicants/nonexistent", headers=auth_headers)
        assert recorder.request_count == 1
