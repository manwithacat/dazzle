"""Cookie name conventions for tenant_host: apps (#1289 slice 4).

Apps without any `tenant_host:` block keep the legacy `dazzle_session`
cookie name. Apps with a `tenant_host:` block switch to a
convention-based name keyed off the `app <name>` declaration:

    * ``__Host-<app>_session`` for tenant-bound sessions (Path=/, no Domain)
    * ``__Secure-<app>_admin`` for canonical-host super-admin sessions
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise_app_name(name: str) -> str:
    """Lowercase, then collapse any non-[a-z0-9] run to a single underscore.

    Trailing/leading underscores are stripped so the resulting token is a
    valid cookie-name-fragment per RFC 6265 token rules.
    """
    lowered = name.lower()
    collapsed = _NON_ALNUM.sub("_", lowered).strip("_")
    if not collapsed:
        raise ValueError(f"app name {name!r} produces an empty normalised token")
    return collapsed


def host_cookie_name(app_name: str) -> str:
    return f"__Host-{normalise_app_name(app_name)}_session"


def apex_cookie_name(app_name: str) -> str:
    return f"__Secure-{normalise_app_name(app_name)}_admin"


def choose_session_cookie_name(
    *,
    app_name: str,
    is_canonical_host: bool,
    user_role: str,
    super_admin_role: str,
) -> str:
    """Login-flow decision tree (spec §Cookie wiring).

    The apex cookie is only set when both:
      * the login request landed on a canonical host, AND
      * the authenticated user holds the configured super-admin role.

    Every other authenticated request gets the host-bound cookie.
    """
    if is_canonical_host and user_role == super_admin_role:
        return apex_cookie_name(app_name)
    return host_cookie_name(app_name)
