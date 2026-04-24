"""Tests for the /dz/consent route surface (v0.61.0 Phase 2)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.compliance.analytics.consent import CONSENT_COOKIE_NAME
from dazzle_back.runtime.consent_routes import create_consent_routes


@pytest.fixture
def eu_app() -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_consent_routes(
            default_jurisdiction="EU",
            privacy_page_url="/privacy",
        )
    )
    return app


@pytest.fixture
def us_app() -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_consent_routes(
            default_jurisdiction="US",
            privacy_page_url="/privacy",
        )
    )
    return app


class TestConsentStateEndpoint:
    def test_eu_unset_cookie_returns_denied_and_undecided(self, eu_app: FastAPI) -> None:
        client = TestClient(eu_app)
        response = client.get("/dz/consent/state")
        assert response.status_code == 200
        data = response.json()
        assert data["undecided"] is True
        assert data["analytics"] == "denied"
        assert data["advertising"] == "denied"
        assert data["functional"] == "granted"

    def test_us_unset_cookie_returns_granted_and_undecided(self, us_app: FastAPI) -> None:
        client = TestClient(us_app)
        response = client.get("/dz/consent/state")
        assert response.status_code == 200
        data = response.json()
        assert data["undecided"] is True
        assert data["analytics"] == "granted"
        assert data["advertising"] == "granted"


class TestPostConsent:
    def test_post_sets_cookie(self, eu_app: FastAPI) -> None:
        client = TestClient(eu_app)
        response = client.post(
            "/dz/consent",
            json={
                "analytics": True,
                "advertising": False,
                "personalization": False,
                "functional": True,
            },
        )
        assert response.status_code == 204
        assert CONSENT_COOKIE_NAME in client.cookies

    def test_round_trip_post_then_get(self, eu_app: FastAPI) -> None:
        client = TestClient(eu_app)
        client.post(
            "/dz/consent",
            json={
                "analytics": True,
                "advertising": True,
                "personalization": False,
                "functional": True,
            },
        )
        response = client.get("/dz/consent/state")
        data = response.json()
        assert data["undecided"] is False
        assert data["analytics"] == "granted"
        assert data["advertising"] == "granted"
        assert data["personalization"] == "denied"

    def test_missing_keys_default_to_denied(self, eu_app: FastAPI) -> None:
        client = TestClient(eu_app)
        client.post("/dz/consent", json={"analytics": True})
        response = client.get("/dz/consent/state")
        data = response.json()
        assert data["analytics"] == "granted"
        assert data["advertising"] == "denied"
        assert data["personalization"] == "denied"

    def test_invalid_json_rejected(self, eu_app: FastAPI) -> None:
        client = TestClient(eu_app)
        response = client.post(
            "/dz/consent",
            headers={"Content-Type": "application/json"},
            content=b"not-json",
        )
        assert response.status_code == 400

    def test_non_object_body_rejected(self, eu_app: FastAPI) -> None:
        client = TestClient(eu_app)
        response = client.post("/dz/consent", json=[1, 2, 3])
        assert response.status_code == 400

    def test_functional_always_granted_regardless_of_input(self, eu_app: FastAPI) -> None:
        """POST with functional=False must still persist functional=granted —
        functional storage is essential and cannot be opted-out of."""
        client = TestClient(eu_app)
        client.post(
            "/dz/consent",
            json={
                "analytics": False,
                "advertising": False,
                "personalization": False,
                "functional": False,
            },
        )
        response = client.get("/dz/consent/state")
        data = response.json()
        assert data["functional"] == "granted"


class TestCookieAttributes:
    def test_cookie_has_correct_attributes(self, eu_app: FastAPI) -> None:
        client = TestClient(eu_app)
        response = client.post(
            "/dz/consent",
            json={
                "analytics": True,
                "advertising": False,
                "personalization": False,
                "functional": True,
            },
        )
        set_cookie = response.headers.get("set-cookie", "")
        assert CONSENT_COOKIE_NAME in set_cookie
        assert "Path=/" in set_cookie
        assert "samesite=lax" in set_cookie.lower()
        # Max-Age should be 13 months worth of seconds.
        assert "Max-Age=" in set_cookie

    def test_cookie_value_decodes_to_valid_state(self, eu_app: FastAPI) -> None:
        """Verify the cookie parses server-side into the expected state.

        Uses the real round-trip (POST + GET) so we test the transport
        quoting/unquoting path rather than trusting the client-side raw."""
        client = TestClient(eu_app)
        client.post(
            "/dz/consent",
            json={
                "analytics": True,
                "advertising": False,
                "personalization": False,
                "functional": True,
            },
        )
        state = client.get("/dz/consent/state").json()
        assert state["analytics"] == "granted"
        assert state["advertising"] == "denied"
        assert state["undecided"] is False
        assert state["decided_at"] is not None
