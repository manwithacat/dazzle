"""Consent endpoints must be CSRF-exempt (#868).

The consent banner is served on anonymous marketing pages that don't carry
a CSRF token — no `<meta name="csrf-token">` tag, no `dazzle_csrf` cookie
issued to unauthenticated sessions. Before this fix, `POST /dz/consent`
returned 403 on every banner click, leaving users stuck at a modal they
couldn't dismiss.

The endpoints are idempotent cookie-setters (writing `dz_consent_v2`) and
carry no authority-escalating side effects, so exempting them from CSRF
is the correct posture. Same-origin enforcement stays via the client-side
`credentials: "same-origin"` policy in dz-consent.js.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle_back.runtime.consent_routes import create_consent_routes
from dazzle_back.runtime.csrf import CSRFConfig, CSRFMiddleware


class TestCSRFExemptPaths:
    def test_default_config_exempts_consent_endpoints(self) -> None:
        config = CSRFConfig()
        assert "/dz/consent" in config.exempt_paths
        assert "/dz/consent/banner" in config.exempt_paths
        assert "/dz/consent/state" in config.exempt_paths


class TestConsentEndpointBehindCSRFMiddleware:
    """End-to-end smoke: CSRF middleware with default config lets consent
    endpoints through, matching how `apply_csrf_protection` mounts them."""

    def _make_app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(
            create_consent_routes(default_jurisdiction="EU", privacy_page_url="/privacy")
        )
        app.add_middleware(CSRFMiddleware, config=CSRFConfig(enabled=True))
        return app

    def test_post_consent_without_csrf_token_returns_204(self) -> None:
        """Matches real AegisMark call: no `X-CSRF-Token` header, no token
        cookie — pre-fix this was 403, post-fix it's 204 (consent stored)."""
        client = TestClient(self._make_app())
        response = client.post(
            "/dz/consent",
            json={
                "analytics": True,
                "advertising": True,
                "personalization": True,
                "functional": True,
            },
        )
        assert response.status_code == 204, response.text

    def test_get_consent_state_without_csrf_token_returns_200(self) -> None:
        client = TestClient(self._make_app())
        response = client.get("/dz/consent/state")
        assert response.status_code == 200

    def test_get_consent_banner_without_csrf_token_returns_200(self) -> None:
        client = TestClient(self._make_app())
        response = client.get("/dz/consent/banner")
        # Endpoint returns HTML (or empty) — either way, NOT 403.
        assert response.status_code in (200, 204)

    def test_other_post_still_challenges_csrf(self) -> None:
        """Sanity: the middleware isn't globally disabled — a non-exempt
        POST without a token still 403s."""
        app = FastAPI()

        @app.post("/protected")
        def _protected() -> dict[str, bool]:
            return {"ok": True}

        app.add_middleware(CSRFMiddleware, config=CSRFConfig(enabled=True))
        client = TestClient(app)
        response = client.post("/protected", json={})
        assert response.status_code == 403
