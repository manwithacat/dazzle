"""Per-request session cookie naming for tenant_host: apps (#1289 follow-up).

Single-tenant apps (no ``tenant_host:`` block) keep the legacy
``dazzle_session`` cookie name. Apps with ``tenant_host:`` switch to
the spec's convention-based names:

* ``__Host-<app>_session`` — Path=/, Secure, no Domain, scoped to a
  single tenant host (the browser refuses to send it to any other host).
* ``__Secure-<app>_admin`` — issued only on a canonical (apex) host for
  users carrying the super-admin role.

The choice is per-request because it depends on whether the request
landed on a canonical host and on the authenticated user's roles.

These helpers wrap the lower-level naming primitives in
``dazzle.http.runtime.tenant.cookies`` with the request-shape glue
(read ``app.state.tenant_host``, ``Host`` header, etc) so route
handlers don't need to know that plumbing.

The browser-prefix mechanics (``__Host-`` / ``__Secure-`` enforcement)
provide the primary cross-tenant isolation; the cross-tenant guard
shipped in v0.80.18 is belt-and-suspenders for non-browser clients.
"""

from __future__ import annotations

from typing import Any

LEGACY_NAME = "dazzle_session"


def _tenant_cfg(request: Any) -> Any | None:
    """Return the ``app.state.tenant_host`` marker if (and only if) it
    looks like a real ``_TenantStateMarker`` — i.e. its ``app_name`` is
    a string. Returns ``None`` otherwise so MagicMock'd test fixtures
    and apps without a ``tenant_host:`` block route through the legacy
    code path unchanged.
    """
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    cfg = getattr(state, "tenant_host", None) if state is not None else None
    if cfg is None or not isinstance(getattr(cfg, "app_name", None), str):
        return None
    return cfg


def _request_host(request: Any) -> str:
    headers = getattr(request, "headers", None)
    if headers is None:
        return ""
    raw = headers.get("host") if hasattr(headers, "get") else None
    if not raw:
        return ""
    return str(raw).split(":")[0].lower()


def select_write_name(
    request: Any,
    *,
    user_roles: list[str] | None = None,
    default: str = LEGACY_NAME,
) -> str:
    """Pick the cookie name to use when **writing** a new session cookie
    in a login / signup / 2FA-verify / SSO-callback handler.

    Apps without ``tenant_host:`` always get ``default`` (typically
    ``dazzle_session``). Apps with ``tenant_host:`` get the host-bound
    name on tenant hosts, or the apex name only when the request landed
    on a canonical host *and* the user carries the configured
    super-admin role.

    Role normalisation matches the rest of the auth layer: database
    roles often carry a ``role_`` prefix which is stripped before
    comparing against ``super_admin_role``.
    """
    cfg = _tenant_cfg(request)
    if cfg is None:
        return default

    from dazzle.http.runtime.tenant.cookies import choose_session_cookie_name

    normalised = {r.removeprefix("role_") for r in (user_roles or [])}
    role = cfg.super_admin_role if cfg.super_admin_role in normalised else ""

    return choose_session_cookie_name(
        app_name=cfg.app_name,
        is_canonical_host=_request_host(request) in cfg.canonical_hosts,
        user_role=role,
        super_admin_role=cfg.super_admin_role,
    )


def read_session_id(request: Any, *, default: str = LEGACY_NAME) -> str | None:
    """Read the session-id value from whichever recognised session
    cookie is present on the request, or ``None`` if none of them are.

    Tries the legacy ``default`` name first so existing authenticated
    sessions keep working across the rollout — an app that adopts
    ``tenant_host:`` mid-flight still serves dazzle_session-bound
    sessions until they expire. New logins after adoption issue
    ``__Host-`` / ``__Secure-`` cookies; both old and new can coexist
    during the migration window without forcing users to re-auth.
    """
    cookies = getattr(request, "cookies", None) or {}
    legacy = cookies.get(default)
    if legacy:
        return str(legacy)

    cfg = _tenant_cfg(request)
    if cfg is None:
        return None

    from dazzle.http.runtime.tenant.cookies import apex_cookie_name, host_cookie_name

    found = cookies.get(host_cookie_name(cfg.app_name)) or cookies.get(
        apex_cookie_name(cfg.app_name)
    )
    return str(found) if found else None


def names_to_clear(request: Any, *, default: str = LEGACY_NAME) -> list[str]:
    """All cookie names that could carry a session for this app —
    used by logout / clear flows so any of them in flight get removed
    in a single response, regardless of which one issued the session.
    """
    cfg = _tenant_cfg(request)
    if cfg is None:
        return [default]

    from dazzle.http.runtime.tenant.cookies import apex_cookie_name, host_cookie_name

    return [default, host_cookie_name(cfg.app_name), apex_cookie_name(cfg.app_name)]
