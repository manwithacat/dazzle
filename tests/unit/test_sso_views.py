"""Unit tests for the SSO button-row typed view (Phase 1.C)."""

from __future__ import annotations

from dazzle.http.runtime.auth.auth_views import (
    build_login_magic_link_view,
    build_login_password_view,
)
from dazzle.http.runtime.auth.sso_config import SsoProviderConfig
from dazzle.http.runtime.auth.sso_views import (
    build_sso_button_row,
    render_sso_section,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _google() -> SsoProviderConfig:
    return SsoProviderConfig(
        name="google",
        display_name="Google",
        client_id="id",
        client_secret="secret",
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        scopes="openid email profile",
    )


def _microsoft() -> SsoProviderConfig:
    return SsoProviderConfig(
        name="microsoft",
        display_name="Microsoft",
        client_id="id",
        client_secret="secret",
        discovery_url=(
            "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"
        ),
        scopes="openid email profile User.Read",
    )


def _render(page: object) -> str:
    return FragmentRenderer().render(page)  # type: ignore[arg-type]


# ───────────────── build_sso_button_row ─────────────────


def test_empty_providers_returns_empty_tuple() -> None:
    assert build_sso_button_row(providers=()) == ()


def test_single_provider_renders_continue_with_link() -> None:
    children = build_sso_button_row(providers=[_google()])
    # divider Text + 1 Link = 2 children
    assert len(children) == 2


def test_both_providers_render_two_links() -> None:
    children = build_sso_button_row(providers=[_google(), _microsoft()])
    # divider + 2 Links = 3 children
    assert len(children) == 3


def test_next_url_threads_into_href() -> None:
    children = build_sso_button_row(providers=[_google()], next_url="/app/tasks")
    # The second child is the Google link.
    link = children[1]
    assert "next=/app/tasks" in str(link.href)


def test_next_url_omitted_when_default() -> None:
    children = build_sso_button_row(providers=[_google()])
    link = children[1]
    assert "?next=" not in str(link.href)


def test_render_sso_section_returns_none_when_empty() -> None:
    assert render_sso_section(providers=()) is None


def test_render_sso_section_returns_stack_when_populated() -> None:
    section = render_sso_section(providers=[_google()])
    assert section is not None
    # Stack carries the same children tuple.
    assert len(section.children) == 2


# ───────────────── login view integration ─────────────────


def test_login_magic_link_view_renders_sso_buttons_when_providers_present() -> None:
    page = build_login_magic_link_view(
        page_title="Sign in",
        product_name="Acme",
        sso_providers=(_google(), _microsoft()),
    )
    html = _render(page)
    assert "Continue with Google" in html
    assert "Continue with Microsoft" in html
    assert 'href="/auth/sso/google"' in html
    assert 'href="/auth/sso/microsoft"' in html


def test_login_magic_link_view_omits_sso_buttons_when_no_providers() -> None:
    page = build_login_magic_link_view(
        page_title="Sign in",
        product_name="Acme",
    )
    html = _render(page)
    assert "Continue with" not in html
    assert "/auth/sso/" not in html


def test_login_password_view_renders_sso_buttons_when_providers_present() -> None:
    page = build_login_password_view(
        page_title="Sign in",
        product_name="Acme",
        sso_providers=(_google(),),
    )
    html = _render(page)
    assert "Continue with Google" in html
    assert 'href="/auth/sso/google"' in html


def test_login_view_threads_next_into_sso_link() -> None:
    page = build_login_magic_link_view(
        page_title="Sign in",
        product_name="Acme",
        next_url="/app/tasks",
        sso_providers=(_google(),),
    )
    html = _render(page)
    assert "/auth/sso/google?next=/app/tasks" in html


def test_sso_divider_label_visible() -> None:
    page = build_login_magic_link_view(
        page_title="Sign in",
        product_name="Acme",
        sso_providers=(_google(),),
    )
    html = _render(page)
    assert "or continue with" in html
