"""Per-request session cookie naming tests (#1289 follow-up).

Covers `select_write_name`, `read_session_id`, and `names_to_clear`
across both legacy (no tenant_host:) and tenant_host: app shapes,
including the canonical-host + super-admin → apex-cookie path from
the design spec.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.auth.cookie_name import (
    LEGACY_NAME,
    names_to_clear,
    read_session_id,
    select_write_name,
)
from dazzle.http.runtime.tenant.cookies import apex_cookie_name, host_cookie_name

APP_NAME = "AegisMark"
HOST_COOKIE = host_cookie_name(APP_NAME)
APEX_COOKIE = apex_cookie_name(APP_NAME)


def _tenant_state(
    *,
    canonical: frozenset[str] = frozenset({"app.example.com"}),
    super_admin: str = "super_admin",
) -> SimpleNamespace:
    return SimpleNamespace(
        app_name=APP_NAME,
        canonical_hosts=canonical,
        super_admin_role=super_admin,
    )


def _request(
    *,
    host: str = "acme.example.com",
    cookies: dict[str, str] | None = None,
    tenant_state: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        headers={"host": host},
        cookies=cookies or {},
        app=SimpleNamespace(state=SimpleNamespace(tenant_host=tenant_state)),
    )


# --- select_write_name -------------------------------------------------------


def test_select_write_name_legacy_app_returns_dazzle_session():
    name = select_write_name(_request(tenant_state=None), user_roles=["member"])
    assert name == LEGACY_NAME


def test_select_write_name_tenant_host_request_returns_host_cookie():
    name = select_write_name(
        _request(host="acme.example.com", tenant_state=_tenant_state()),
        user_roles=["member"],
    )
    assert name == HOST_COOKIE


def test_select_write_name_canonical_host_non_admin_returns_host_cookie():
    """Canonical host but non-admin: still gets host-bound cookie per spec."""
    name = select_write_name(
        _request(host="app.example.com", tenant_state=_tenant_state()),
        user_roles=["member"],
    )
    assert name == HOST_COOKIE


def test_select_write_name_canonical_host_super_admin_returns_apex_cookie():
    name = select_write_name(
        _request(host="app.example.com", tenant_state=_tenant_state()),
        user_roles=["super_admin"],
    )
    assert name == APEX_COOKIE


def test_select_write_name_strips_role_prefix():
    name = select_write_name(
        _request(host="app.example.com", tenant_state=_tenant_state()),
        user_roles=["role_super_admin"],
    )
    assert name == APEX_COOKIE


def test_select_write_name_tenant_host_super_admin_on_tenant_host_returns_host_cookie():
    """Super-admins on a tenant host still get the host-bound cookie —
    apex cookies are reserved for the canonical host."""
    name = select_write_name(
        _request(host="acme.example.com", tenant_state=_tenant_state()),
        user_roles=["super_admin"],
    )
    assert name == HOST_COOKIE


def test_select_write_name_honours_custom_default():
    name = select_write_name(_request(tenant_state=None), user_roles=[], default="my_custom")
    assert name == "my_custom"


# --- read_session_id ---------------------------------------------------------


def test_read_session_id_legacy_cookie_preferred_during_rollout():
    """An app that adopts tenant_host: keeps serving legacy sessions
    until they expire — dazzle_session takes priority on read."""
    request = _request(
        cookies={LEGACY_NAME: "legacy-sid", HOST_COOKIE: "new-sid"},
        tenant_state=_tenant_state(),
    )
    assert read_session_id(request) == "legacy-sid"


def test_read_session_id_falls_back_to_host_cookie():
    request = _request(cookies={HOST_COOKIE: "sid-x"}, tenant_state=_tenant_state())
    assert read_session_id(request) == "sid-x"


def test_read_session_id_falls_back_to_apex_cookie():
    request = _request(cookies={APEX_COOKIE: "admin-sid"}, tenant_state=_tenant_state())
    assert read_session_id(request) == "admin-sid"


def test_read_session_id_no_cookie_returns_none():
    request = _request(cookies={}, tenant_state=_tenant_state())
    assert read_session_id(request) is None


def test_read_session_id_legacy_app_only_reads_default():
    request = _request(cookies={HOST_COOKIE: "ignored"}, tenant_state=None)
    assert read_session_id(request) is None


# --- names_to_clear ----------------------------------------------------------


def test_names_to_clear_legacy_app_returns_only_default():
    names = names_to_clear(_request(tenant_state=None))
    assert names == [LEGACY_NAME]


def test_names_to_clear_tenant_host_returns_all_three():
    names = names_to_clear(_request(tenant_state=_tenant_state()))
    assert names == [LEGACY_NAME, HOST_COOKIE, APEX_COOKIE]


# --- defensive shape check (MagicMock guard) ---------------------------------


def test_legacy_path_when_tenant_host_attr_is_not_a_marker():
    """If `app.state.tenant_host` exists but its `app_name` isn't a
    string, fall back to legacy behaviour. Prevents MagicMock'd test
    fixtures from spuriously activating tenant-host mode."""
    bogus = SimpleNamespace(app_name=object())
    request = _request(tenant_state=bogus)
    assert select_write_name(request, user_roles=["super_admin"]) == LEGACY_NAME
    assert names_to_clear(request) == [LEGACY_NAME]
