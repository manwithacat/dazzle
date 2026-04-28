"""
Regression tests for the auth_page_wrapper macro (#842).

Pins the fact that the macro emits exactly the card div — not a nested
wrapper div with its own background. The body already carries the
.dz-auth-page class which provides the gradient + flex centering; a
second wrapper shrinks to max-w-sm and paints a translucent vertical
strip over the gradient.
"""

from __future__ import annotations

import re

SITESPEC: dict = {"brand": {"product_name": "TestApp"}}


def _render_login() -> str:
    from dazzle_ui.runtime.site_context import build_site_auth_context
    from dazzle_ui.runtime.template_renderer import render_site_page

    ctx = build_site_auth_context(SITESPEC, "login")
    return render_site_page("site/auth/login.html", ctx)


class TestAuthPageWrapper:
    def test_body_carries_dz_auth_page_class(self) -> None:
        """The body element must carry .dz-auth-page — that's where the gradient lives."""
        html = _render_login()
        # body_class block is rendered into the <body class="..."> attr
        body_match = re.search(r"<body[^>]*class=\"([^\"]+)\"", html)
        assert body_match is not None, "no <body class=...> found"
        assert "dz-auth-page" in body_match.group(1)

    def test_card_has_no_screen_height_wrapper(self) -> None:
        """Post-#842: the macro must not emit its own min-h-screen wrapper.

        That redundant wrapper shrunk to max-w-sm and painted a vertical
        strip over the .dz-auth-page gradient.
        """
        html = _render_login()
        assert (
            "min-h-screen flex items-center justify-center p-4 bg-[hsl(var(--muted)/0.3)]"
            not in html
        )

    def test_card_max_width_still_rendered(self) -> None:
        """The inner card div must still be present.

        v0.62 CSS refactor: card chrome (max-width 24rem, padding,
        border, shadow) lives on .dz-auth-card rule rather than inline
        `w-full max-w-sm bg-[hsl(var(--card))] border ...` Tailwind."""
        html = _render_login()
        assert "dz-auth-card" in html

        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/fragments.css"
        ).read_text()
        card_block = css.split(".dz-auth-card {")[1].split("}")[0]
        assert "max-width: 24rem" in card_block  # 24rem = previous max-w-sm

    def test_product_name_rendered_in_card(self) -> None:
        html = _render_login()
        assert "TestApp" in html
