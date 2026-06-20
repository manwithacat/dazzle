"""FastAPI adapter for the cross-tenant guard (#1289 follow-up to slice 5).

`guard.py` is intentionally framework-free — pure truth-table logic.
This module bridges it to FastAPI's `Request` + `AuthContext`:

* sniffs the request cookies via the conventional host/apex names from
  `cookies.py` to decide which cookie kind authenticated this request
* normalises `AuthContext.roles` (list, with optional `role_` prefix) to
  the single `user_role` string the truth table expects
* translates the three typed guard exceptions to `HTTPException(403)`

The adapter is a no-op when `app.state.tenant_host` is `None` (i.e. the
app has no `tenant_host:` block) so legacy single-tenant apps are
unaffected.

Until the cookie-naming follow-up threads `__Host-<app>_session` /
`__Secure-<app>_admin` through the login routes, `request.cookies`
won't carry either of those names, so `cookie_kind` stays `None` and
`check_cross_tenant()` returns `PASS`. The wiring is dormant but
present, so the day the cookie rename ships the guard activates without
further changes here.
"""

from __future__ import annotations

from typing import Any, Literal

from dazzle.http.runtime.tenant.cookies import apex_cookie_name, host_cookie_name
from dazzle.http.runtime.tenant.guard import (
    ApexCookieNotSuperAdmin,
    CrossTenantForbidden,
    HostCookieMissingTenant,
    check_cross_tenant,
)


def enforce_cross_tenant(request: Any, auth_context: Any) -> None:
    """Apply the cross-tenant guard to an authenticated request.

    Call after the session has been validated and the user loaded;
    raises `HTTPException(403)` on a guard violation, returns `None`
    otherwise.
    """
    tenant_cfg = _resolve_tenant_state(request)
    if tenant_cfg is None:
        return

    cookies = _cookies(request)
    cookie_kind = _classify_cookie(cookies, tenant_cfg.app_name)

    user = getattr(auth_context, "user", None)
    session_tenant_slug = getattr(user, "tenant_slug", None) if user is not None else None

    user_role = _pick_user_role(
        getattr(auth_context, "roles", []) or [],
        tenant_cfg.super_admin_role,
    )

    try:
        check_cross_tenant(
            cookie_kind=cookie_kind,
            session_tenant_slug=session_tenant_slug,
            request_tenant=getattr(getattr(request, "state", None), "tenant", None),
            user_role=user_role,
            super_admin_role=tenant_cfg.super_admin_role,
        )
    except (CrossTenantForbidden, HostCookieMissingTenant, ApexCookieNotSuperAdmin) as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _resolve_tenant_state(request: Any) -> Any | None:
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    cfg = getattr(state, "tenant_host", None) if state is not None else None
    # Only honour a real TenantStateMarker. MagicMock'd test fixtures will
    # have a truthy `tenant_host` attribute whose `app_name` isn't a string —
    # guard against that so we don't wedge unrelated tests.
    if cfg is None or not isinstance(getattr(cfg, "app_name", None), str):
        return None
    return cfg


def _cookies(request: Any) -> dict[str, str]:
    raw = getattr(request, "cookies", None)
    if raw is None:
        return {}
    try:
        return dict(raw)
    except (TypeError, ValueError):
        return {}


def _classify_cookie(cookies: dict[str, str], app_name: str) -> Literal["host", "apex"] | None:
    if cookies.get(host_cookie_name(app_name)):
        return "host"
    if cookies.get(apex_cookie_name(app_name)):
        return "apex"
    return None


def _pick_user_role(raw_roles: list[str], super_admin_role: str) -> str:
    """Reduce AuthContext.roles to the single role the truth table checks.

    Database roles use a ``role_`` prefix; persona IDs don't — strip it so
    membership comparisons are consistent with the rest of the auth layer.
    Returns the super-admin role if held (so apex cookies pass), otherwise
    any held role (so apex cookies on a non-admin raise), otherwise ``""``.
    """
    normalised = {r.removeprefix("role_") for r in raw_roles}
    if super_admin_role in normalised:
        return super_admin_role
    return next(iter(normalised), "")
