"""Per-request session cookie naming tests (#1289 follow-up).

Covers `select_write_name`, `read_session_id`, and `names_to_clear`
across both legacy (no tenant_host:) and tenant_host: app shapes,
including the canonical-host + super-admin → apex-cookie path from
the design spec.

Security-sensitive (#1518 history): each parametrized row below pins one
branch's exact expectation — do not merge or drop rows without re-deriving
them from the design spec.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize(
    ("host", "tenant", "user_roles", "expected"),
    [
        pytest.param(
            "acme.example.com",
            False,
            ["member"],
            LEGACY_NAME,
            id="legacy-app-returns-dazzle-session",
        ),
        pytest.param(
            "acme.example.com",
            True,
            ["member"],
            HOST_COOKIE,
            id="tenant-host-request-returns-host-cookie",
        ),
        # Canonical host but non-admin: still gets host-bound cookie per spec.
        pytest.param(
            "app.example.com",
            True,
            ["member"],
            HOST_COOKIE,
            id="canonical-host-non-admin-returns-host-cookie",
        ),
        pytest.param(
            "app.example.com",
            True,
            ["super_admin"],
            APEX_COOKIE,
            id="canonical-host-super-admin-returns-apex-cookie",
        ),
        pytest.param(
            "app.example.com",
            True,
            ["role_super_admin"],
            APEX_COOKIE,
            id="strips-role-prefix",
        ),
        # Super-admins on a tenant host still get the host-bound cookie —
        # apex cookies are reserved for the canonical host.
        pytest.param(
            "acme.example.com",
            True,
            ["super_admin"],
            HOST_COOKIE,
            id="super-admin-on-tenant-host-returns-host-cookie",
        ),
    ],
)
def test_select_write_name(host: str, tenant: bool, user_roles: list[str], expected: str) -> None:
    request = _request(host=host, tenant_state=_tenant_state() if tenant else None)
    assert select_write_name(request, user_roles=user_roles) == expected


def test_select_write_name_honours_custom_default():
    name = select_write_name(_request(tenant_state=None), user_roles=[], default="my_custom")
    assert name == "my_custom"


# --- read_session_id ---------------------------------------------------------


@pytest.mark.parametrize(
    ("cookies", "tenant", "expected"),
    [
        # An app that adopts tenant_host: keeps serving legacy sessions
        # until they expire — dazzle_session takes priority on read.
        pytest.param(
            {LEGACY_NAME: "legacy-sid", HOST_COOKIE: "new-sid"},
            True,
            "legacy-sid",
            id="legacy-cookie-preferred-during-rollout",
        ),
        pytest.param(
            {HOST_COOKIE: "sid-x"},
            True,
            "sid-x",
            id="falls-back-to-host-cookie",
        ),
        pytest.param(
            {APEX_COOKIE: "admin-sid"},
            True,
            "admin-sid",
            id="falls-back-to-apex-cookie",
        ),
        pytest.param({}, True, None, id="no-cookie-returns-none"),
        # A legacy app must never honour a tenant-shaped cookie name.
        pytest.param(
            {HOST_COOKIE: "ignored"},
            False,
            None,
            id="legacy-app-only-reads-default",
        ),
    ],
)
def test_read_session_id(cookies: dict[str, str], tenant: bool, expected: str | None) -> None:
    request = _request(cookies=cookies, tenant_state=_tenant_state() if tenant else None)
    if expected is None:
        assert read_session_id(request) is None
    else:
        assert read_session_id(request) == expected


# --- names_to_clear ----------------------------------------------------------


@pytest.mark.parametrize(
    ("tenant", "expected"),
    [
        pytest.param(False, [LEGACY_NAME], id="legacy-app-returns-only-default"),
        pytest.param(
            True,
            [LEGACY_NAME, HOST_COOKIE, APEX_COOKIE],
            id="tenant-host-returns-all-three",
        ),
    ],
)
def test_names_to_clear(tenant: bool, expected: list[str]) -> None:
    request = _request(tenant_state=_tenant_state() if tenant else None)
    assert names_to_clear(request) == expected


# --- defensive shape check (MagicMock guard) ---------------------------------


def test_legacy_path_when_tenant_host_attr_is_not_a_marker():
    """If `app.state.tenant_host` exists but its `app_name` isn't a
    string, fall back to legacy behaviour. Prevents MagicMock'd test
    fixtures from spuriously activating tenant-host mode."""
    bogus = SimpleNamespace(app_name=object())
    request = _request(tenant_state=bogus)
    assert select_write_name(request, user_roles=["super_admin"]) == LEGACY_NAME
    assert names_to_clear(request) == [LEGACY_NAME]
