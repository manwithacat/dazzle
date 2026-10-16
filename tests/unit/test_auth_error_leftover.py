"""Auth leftover ?error= tokens must not invent a clean page (cycle 2221).

Login used to omit leftover ``?error=zzz`` as absent and invented a clean
sign-in. Social SSO's ``sso_{reason}`` tokens vanished the same way.
Valid declared tokens ride; leftover stays put (400, no invented
clean page). Live simple_task ``/login``. Oral #95.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.auth_views import (
    LOGIN_ERROR_MESSAGES,
    leftover_honest_auth_error,
)
from dazzle.http.runtime.auth.org_context_routes import create_org_context_routes
from dazzle.http.runtime.site_routes import create_auth_page_routes


@pytest.mark.parametrize(
    ("raw", "declared", "expected"),
    [
        ("invalid_credentials", ("invalid_credentials", "sso_failed"), "invalid_credentials"),
        ("sso_provider_unknown", ("sso_provider_unknown", "sso_failed"), "sso_provider_unknown"),
        ("", ("invalid_credentials",), ""),
        (None, ("invalid_credentials",), ""),
        ("   ", ("invalid_credentials",), ""),
        ("zzz", ("invalid_credentials",), None),
        ("ghost", ("invalid_credentials",), None),
        ("sso_failed ", ("sso_failed",), "sso_failed"),
        ("INVALID_CREDENTIALS", ("invalid_credentials",), None),
    ],
    ids=[
        "valid-credentials",
        "valid-sso-provider-unknown",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "valid-strip",
        "leftover-case",
    ],
)
def test_leftover_honest_auth_error_does_not_invent(
    raw: object, declared: tuple[str, ...], expected: str | None
) -> None:
    assert leftover_honest_auth_error(raw, declared) == expected


def _site_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_auth_page_routes({"brand": {"product_name": "Acme"}}))
    return TestClient(app)


def _org_client() -> TestClient:
    app = FastAPI()

    class _Store:
        def validate_session(self, _sid: object) -> object:
            return type("Ctx", (), {"is_authenticated": False, "user": None})()

    app.state.auth_store = _Store()
    app.include_router(create_org_context_routes())
    return TestClient(app)


_LOGIN_FORM = "Sign in"

# (client, url, status, present, absent). A leftover token answers 400 with an
# "Unknown … error" page and never the clean form; a declared token rides (200)
# with its own message; no token renders the plain form.
_CASES = [
    pytest.param(
        _site_client,
        "/login",
        200,
        ("Send sign-in link", _LOGIN_FORM),
        ("Unknown login error",),
        id="login-no-error-renders-form",
    ),
    pytest.param(
        _site_client,
        "/login?error=zzz",
        400,
        ("Unknown login error",),
        (_LOGIN_FORM, "didn't match"),
        id="login-leftover-zzz-400-no-clean-form",
    ),
    pytest.param(
        _site_client,
        "/login?error=ghost",
        400,
        ("Unknown login error",),
        (_LOGIN_FORM, "We couldn't complete the sign-in"),
        id="login-leftover-ghost-400-no-invented-banner",
    ),
    pytest.param(
        _site_client,
        "/login?error=invalid_credentials",
        200,
        ("That email and password didn't match. Try again.",),
        (),
        id="login-invalid-credentials-rides",
    ),
    *[
        pytest.param(
            _site_client,
            f"/login?error={token}",
            200,
            (LOGIN_ERROR_MESSAGES[token],),
            (),
            id=f"login-{token.replace('_', '-')}-rides",
        )
        for token in (
            "sso_provider_unknown",
            # Enterprise OIDC (DD-013, EA-2).
            "sso_no_connection",
            "sso_unavailable",
            "sso_domain_not_verified",
            "sso_unverified_fallback",
            "sso_no_membership",
        )
    ],
    pytest.param(
        _site_client,
        "/signup?error=zzz",
        400,
        ("Unknown signup error",),
        (),
        id="signup-leftover-400",
    ),
    pytest.param(
        _site_client,
        "/signup?error=already_registered",
        200,
        ("already exists",),
        (),
        id="signup-already-registered-rides",
    ),
    pytest.param(
        _site_client,
        "/reset-password?error=zzz",
        400,
        ("Unknown reset error",),
        (),
        id="reset-leftover-400",
    ),
    pytest.param(
        _site_client,
        "/reset-password?error=invalid",
        200,
        ("invalid or expired",),
        (),
        id="reset-invalid-rides",
    ),
    pytest.param(
        _org_client,
        "/auth/select-org?error=zzz",
        400,
        ("Unknown org error",),
        (),
        id="select-org-leftover-400",
    ),
    pytest.param(
        _org_client,
        "/auth/select-org?error=invalid_org",
        200,
        ("That organization isn't available",),
        (),
        id="select-org-invalid-org-rides",
    ),
]


@pytest.mark.parametrize(("client", "url", "status", "present", "absent"), _CASES)
def test_error_token_page(
    client: object, url: str, status: int, present: tuple[str, ...], absent: tuple[str, ...]
) -> None:
    resp = client().get(url)  # type: ignore[operator]
    assert resp.status_code == status
    for text in present:
        assert text in resp.text, text
    for text in absent:
        assert text not in resp.text, text
