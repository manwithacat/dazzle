"""Tests for tenant cookie helpers (#1289 slice 4)."""

from __future__ import annotations

import pytest

from dazzle.http.runtime.tenant.cookies import (
    apex_cookie_name,
    choose_session_cookie_name,
    host_cookie_name,
    normalise_app_name,
)


def test_normalise_app_name_lowercase_and_underscores():
    assert normalise_app_name("AegisMark-Prod") == "aegismark_prod"
    assert normalise_app_name("acme") == "acme"
    assert normalise_app_name("a.b.c") == "a_b_c"


def test_host_cookie_name_uses_prefix_and_normalised_app():
    assert host_cookie_name("Acme-App") == "__Host-acme_app_session"


def test_apex_cookie_name_uses_secure_prefix():
    assert apex_cookie_name("Acme-App") == "__Secure-acme_app_admin"


@pytest.mark.parametrize("name", ["", "   ", "!@#$"])
def test_normalise_rejects_empty_or_non_alnum_only(name):
    with pytest.raises(ValueError):
        normalise_app_name(name)


def test_choose_session_cookie_falls_to_host_when_tenant_present():
    name = choose_session_cookie_name(
        app_name="acme",
        is_canonical_host=False,
        user_role="member",
        super_admin_role="super_admin",
    )
    assert name == "__Host-acme_session"


def test_choose_session_cookie_uses_apex_when_canonical_and_super_admin():
    name = choose_session_cookie_name(
        app_name="acme",
        is_canonical_host=True,
        user_role="super_admin",
        super_admin_role="super_admin",
    )
    assert name == "__Secure-acme_admin"


def test_choose_session_cookie_falls_back_to_host_for_non_admin_on_canonical():
    name = choose_session_cookie_name(
        app_name="acme",
        is_canonical_host=True,
        user_role="member",
        super_admin_role="super_admin",
    )
    assert name == "__Host-acme_session"
