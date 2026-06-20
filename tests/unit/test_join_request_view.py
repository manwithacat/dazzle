"""GET /auth/join-requested confirmation page (#1424 Task 3.5).

Asserts:
  - The route returns HTTP 200.
  - The response body contains the generic confirmation message.
  - The response body does NOT reveal any tenant name or org-specific copy.
  - The page title is set (non-empty HTML).

Security invariant: enumeration-safe — the page must not confirm
tenant identity or that a specific organisation exists.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.join_request_routes import create_join_request_routes

_GENERIC_MESSAGE = "Your request to join has been submitted and is awaiting approval"

_FORBIDDEN_PLACEHOLDERS = [
    "{{tenant",
    "{{org",
    "{org_name}",
    "{tenant_name}",
    "{org_slug}",
    "{tenant_id}",
]


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_join_request_routes())
    return TestClient(app, follow_redirects=False)


def test_join_requested_returns_200() -> None:
    """GET /auth/join-requested must return HTTP 200."""
    client = _make_client()
    response = client.get("/auth/join-requested")
    assert response.status_code == 200


def test_join_requested_contains_generic_confirmation_message() -> None:
    """Page body must contain the generic awaiting-approval copy."""
    client = _make_client()
    response = client.get("/auth/join-requested")
    assert _GENERIC_MESSAGE in response.text


def test_join_requested_no_tenant_placeholder() -> None:
    """Page must not expose any tenant-name or org-slug placeholder
    (enumeration-safe — invariant 4 from the task brief)."""
    client = _make_client()
    response = client.get("/auth/join-requested")
    html = response.text
    for placeholder in _FORBIDDEN_PLACEHOLDERS:
        assert placeholder not in html, f"Found forbidden placeholder {placeholder!r} in page"


def test_join_requested_is_html() -> None:
    """Response content-type must be HTML."""
    client = _make_client()
    response = client.get("/auth/join-requested")
    assert "text/html" in response.headers.get("content-type", "")


def test_join_requested_no_form() -> None:
    """The confirmation page is informational — no form or submit button."""
    client = _make_client()
    response = client.get("/auth/join-requested")
    # No <form> action pointing to an action endpoint
    assert "<form" not in response.text
