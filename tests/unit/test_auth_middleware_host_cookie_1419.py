"""#1419 — AuthMiddleware.get_auth_context must be __Host-/__Secure- cookie aware.

Under `tenant_host:`, new logins write `__Host-<app>_session`, but
`get_auth_context` read a single fixed name (`dazzle_session`) → empty
AuthContext → every workspace 403s while entity surfaces (which read via the
tenant-aware `read_session_id`) work. The fix routes get_auth_context through
the same `read_session_id` primitive.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.back.runtime.auth.middleware import AuthMiddleware


class _Store:
    """Records the session id handed to validate_session; returns a sentinel ctx."""

    def __init__(self) -> None:
        self.called_with: str | None = None

    def validate_session(self, session_id: str) -> object:
        self.called_with = session_id
        return SimpleNamespace(roles=["author"], is_authenticated=True)


def _req(cookies: dict[str, str], app_name: str | None) -> SimpleNamespace:
    tenant_host = SimpleNamespace(app_name=app_name) if app_name else None
    return SimpleNamespace(
        cookies=cookies,
        app=SimpleNamespace(state=SimpleNamespace(tenant_host=tenant_host)),
    )


class TestGetAuthContextHostCookie:
    def test_host_cookie_resolved_under_tenant_host(self) -> None:
        # The exact repro: only the __Host- cookie is present, no legacy name.
        store = _Store()
        ctx = AuthMiddleware(store).get_auth_context(
            _req({"__Host-myapp_session": "SID123"}, app_name="myapp")
        )
        assert store.called_with == "SID123"
        assert ctx.roles == ["author"]

    def test_legacy_cookie_still_resolved(self) -> None:
        # Single-tenant / migration window: legacy dazzle_session still works.
        store = _Store()
        AuthMiddleware(store).get_auth_context(_req({"dazzle_session": "LEG1"}, app_name="myapp"))
        assert store.called_with == "LEG1"

    def test_no_session_cookie_returns_empty_context(self) -> None:
        store = _Store()
        ctx = AuthMiddleware(store).get_auth_context(_req({}, app_name="myapp"))
        assert store.called_with is None  # validate_session never called
        assert not getattr(ctx, "roles", None)  # empty AuthContext


class _SessionStore:
    """validate_session returns a full session context (the JWT fallback reads .user)."""

    def __init__(self) -> None:
        self.called_with: str | None = None

    def validate_session(self, session_id: str) -> object:
        self.called_with = session_id
        return SimpleNamespace(
            is_authenticated=True,
            roles=["author"],
            user=SimpleNamespace(id="u1", email="a@example.com"),
        )


class _NoJWT:
    def get_auth_context(self, request: object) -> object:
        return SimpleNamespace(is_authenticated=False)


class TestJwtMiddlewareSessionFallbackHostCookie:
    """#1419 audit: the JWT middleware's session fallback had the same single-name bug."""

    def test_session_fallback_resolves_host_cookie(self) -> None:
        from dazzle.back.runtime.jwt_middleware import DualAuthMiddleware

        store = _SessionStore()
        mw = DualAuthMiddleware(_NoJWT(), store)
        result = mw.get_auth_context(_req({"__Host-myapp_session": "SID9"}, app_name="myapp"))
        assert store.called_with == "SID9"
        assert result["auth_type"] == "session"
        assert result["is_authenticated"] is True
