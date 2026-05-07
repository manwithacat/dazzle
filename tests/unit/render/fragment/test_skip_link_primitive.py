"""SkipLink primitive — a11y skip-link (P17 Phase 9)."""

import pytest

from dazzle.render.fragment import AppShell, Page, SkipLink, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── Construction ─────────────────────────


def test_skip_link_default_target_and_text() -> None:
    s = SkipLink()
    assert s.target == "#main-content"
    assert s.text == "Skip to main content"


def test_skip_link_custom_target_and_text() -> None:
    s = SkipLink(target="#content", text="Skip to content")
    assert s.target == "#content"
    assert s.text == "Skip to content"


def test_skip_link_rejects_empty_target() -> None:
    with pytest.raises(ValueError, match="non-empty target"):
        SkipLink(target="")


def test_skip_link_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="non-empty text"):
        SkipLink(text="")


# ───────────────── Renderer output ─────────────────────


def test_skip_link_renders_anchor_with_dz_class() -> None:
    html = _render(SkipLink())
    assert '<a href="#main-content" class="dz-skip-link">Skip to main content</a>' == html


def test_skip_link_target_is_attribute_escaped() -> None:
    html = _render(SkipLink(target='#"><script>'))
    assert "<script>" not in html
    assert "&quot;" in html or "&#x27;" in html or "&#34;" in html


def test_skip_link_text_is_html_escaped() -> None:
    html = _render(SkipLink(target="#x", text="<b>Skip</b>"))
    assert "<b>Skip</b>" not in html
    assert "&lt;b&gt;Skip&lt;/b&gt;" in html


# ───────────────── AppShell auto-emit ─────────────────


def test_app_shell_auto_emits_skip_link_at_top() -> None:
    """AppShell emits a skip-link as the first child of its root div
    so keyboard caret reaches it before any nav content."""
    html = _render(AppShell(body=Text("body")))
    assert '<a href="#main-content" class="dz-skip-link">' in html
    # Skip-link comes BEFORE the main content
    skip_idx = html.index("dz-skip-link")
    main_idx = html.index('<main class="dz-app-main"')
    assert skip_idx < main_idx


def test_app_shell_skip_link_text_is_customisable() -> None:
    html = _render(AppShell(body=Text("body"), skip_link_text="Aller au contenu principal"))
    assert "Aller au contenu principal" in html


def test_app_shell_skip_link_can_be_disabled() -> None:
    """Empty `skip_link_text` disables auto-emission. Rare — almost
    always wrong — but supported for callers with bespoke a11y wiring."""
    html = _render(AppShell(body=Text("body"), skip_link_text=""))
    assert "dz-skip-link" not in html


# ───────────────── Composition with Page ──────────────


def test_page_with_app_shell_includes_skip_link() -> None:
    """End-to-end a11y: a chrome-on app's full-page render includes
    the skip-link as part of AppShell's contract."""
    html = _render(Page(title="X", body=AppShell(body=Text("main"))))
    assert '<a href="#main-content" class="dz-skip-link">' in html
    assert '<main class="dz-app-main" id="main-content">' in html
