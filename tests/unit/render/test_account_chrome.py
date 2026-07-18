"""App-shell account chrome — identity, Home, logout in topbar trailing."""

from __future__ import annotations

from dazzle.render.context import PageContext
from dazzle.render.dispatch import _build_account_trailing, build_app_chrome_page
from dazzle.render.fragment.renderer import FragmentRenderer


def test_account_trailing_shows_email_home_logout() -> None:
    ctx = PageContext(
        page_title="User List",
        app_name="Support Tickets",
        is_authenticated=True,
        user_email="sarah@example.test",
        user_name="manager",
        user_roles=["manager"],
    )
    html = FragmentRenderer().render(_build_account_trailing(ctx))
    assert "Home" in html
    assert 'href="/app"' in html
    assert "sarah@example.test" in html
    assert "Log out" in html
    assert 'data-dazzle-auth-action="logout"' in html
    assert 'action="/auth/logout"' in html
    assert 'method="post"' in html


def test_account_trailing_none_when_anonymous() -> None:
    ctx = PageContext(page_title="Login", app_name="App", is_authenticated=False)
    assert _build_account_trailing(ctx) is None


def test_build_app_chrome_includes_trailing_when_authed() -> None:
    ctx = PageContext(
        page_title="Ops",
        app_name="App",
        is_authenticated=True,
        user_email="a@b.test",
        user_roles=["agent"],
    )
    html = FragmentRenderer().render(build_app_chrome_page(ctx, "<p>x</p>"))
    assert "dz-topbar-trailing" in html
    assert "a@b.test" in html
    assert "Log out" in html
