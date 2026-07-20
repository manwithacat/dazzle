"""Request policies for walk HTTP clients (#1639 CSRF / CyFuture requirements).

Re-exports the shared testing HTTP policy helpers so walk code can keep
importing from ``dazzle.testing.walk.policies``. Implementation lives in
``dazzle.testing.http_policies`` (also used by test_runner, htmx_client,
RBAC harness).
"""

from __future__ import annotations

from dazzle.testing.http_policies import (
    CSRF_COOKIE,
    CSRF_HEADER,
    MUTATING_METHODS,
    SESSION_COOKIE,
    attach_csrf_request_hook,
    cookies_for_playwright,
    csrf_headers,
    csrf_token_from_client,
    extract_csrf_from_set_cookie,
    inject_csrf_headers,
    prime_csrf_cookie,
    prime_csrf_cookie_sync,
)

__all__ = [
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "MUTATING_METHODS",
    "SESSION_COOKIE",
    "attach_csrf_request_hook",
    "cookies_for_playwright",
    "csrf_headers",
    "csrf_token_from_client",
    "extract_csrf_from_set_cookie",
    "inject_csrf_headers",
    "prime_csrf_cookie",
    "prime_csrf_cookie_sync",
]
