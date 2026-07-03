"""HaTchi-MaXchi tranche 1 — bundle carries the new component contracts."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

STATIC = Path(__file__).parents[2] / "src" / "dazzle" / "page" / "runtime" / "static"
HM = Path(__file__).parents[2] / "packages" / "hatchi-maxchi"


def _bundle() -> str:
    from dazzle.page.runtime.css_loader import get_bundled_css

    return get_bundled_css()


@pytest.mark.parametrize(
    "selector",
    [
        ".dz-alert",
        '.dz-alert[data-dz-tone="warning"]',
        ".dz-separator",
        "[data-dz-tooltip]::after",
        ".dz-menu__panel",
        ".dz-menu__item",
        "dialog.dz-alert-dialog",
        ".dz-alert-dialog__actions",
        "input.dz-checkbox",
        "input.dz-radio:checked::before",
        "input.dz-switch:checked",
    ],
)
def test_component_css_in_dev_bundle(selector: str) -> None:
    assert selector in _bundle(), f"{selector} missing from the CSS bundle"


def test_confirm_controller_bundled() -> None:
    import scripts.build_dist as build_dist  # type: ignore[import-not-found]

    names = {p.name for p in build_dist.JS_SOURCES}
    assert "dz-confirm.js" in names, (
        "dz-confirm.js dropped from build_dist.JS_SOURCES — every hx-confirm "
        "would regress to window.confirm"
    )


def test_confirm_controller_intercepts_htmx_confirm() -> None:
    js = (HM / "controllers" / "dz-confirm.js").read_text()
    assert "htmx:confirm" in js
    assert "issueRequest(true)" in js
    assert "data-dz-native-confirm" in js  # opt-out contract
    # user-controlled question must go through textContent, never innerHTML
    assert 'querySelector(".dz-alert-dialog__message").textContent' in js


def test_empty_state_title_uses_text_token() -> None:
    css = (HM / "components" / "fragment-primitives.css").read_text()
    assert ".dz-empty-state__title {\n  color: var(--colour-text);" in css


@pytest.mark.parametrize(
    "selector",
    [
        ".dz-progress__bar",
        ".dz-avatar",
        ".dz-avatar-group .dz-avatar + .dz-avatar",
        ".dz-breadcrumb li + li::before",
        ".dz-toggle-group input:checked + span",
        ".dz-popover__panel",
        ".dz-kbd",
    ],
)
def test_tranche2a_css_in_dev_bundle(selector: str) -> None:
    assert selector in _bundle(), f"{selector} missing from the CSS bundle"


def test_dark_token_block_has_media_fallback() -> None:
    css = (HM / "base" / "design-system.css").read_text()
    assert ':root:not([data-theme="light"])' in css, (
        "the shadow/--dz-* dark overrides must follow prefers-color-scheme "
        "(no-JS/pre-paint dark parity) — the tranche-2A fallback block was removed"
    )


@pytest.mark.parametrize(
    "selector",
    [
        "dialog.dz-command",
        '.dz-command__item[aria-selected="true"]',
        ".dz-command__empty",
        ".dz-hover-card:hover .dz-hover-card__panel",
        ".dz-scroll-area::-webkit-scrollbar-thumb",
    ],
)
def test_tranche2b_css_in_dev_bundle(selector: str) -> None:
    assert selector in _bundle(), f"{selector} missing from the CSS bundle"


def test_command_controller_bundled_and_wired() -> None:
    import scripts.build_dist as build_dist  # type: ignore[import-not-found]

    assert "dz-command.js" in {p.name for p in build_dist.JS_SOURCES}
    js = (HM / "controllers" / "dz-command.js").read_text()
    assert "metaKey" in js and "htmx:afterSwap" in js and "aria-selected" in js


def test_command_dialog_injected_when_endpoint_set() -> None:
    from dazzle.render.fragment import AppShell, Surface, Text
    from dazzle.render.fragment.renderer import FragmentRenderer

    shell = AppShell(
        body=Surface(header=Text("x"), body=Text("y")),
        command_endpoint="/app/command",
    )
    html = FragmentRenderer().render(shell)  # type: ignore[arg-type]
    assert 'dialog class="dz-command"' in html
    assert 'hx-get="/app/command"' in html


def test_command_dialog_absent_without_endpoint() -> None:
    from dazzle.render.fragment import AppShell, Surface, Text
    from dazzle.render.fragment.renderer import FragmentRenderer

    shell = AppShell(body=Surface(header=Text("x"), body=Text("y")))
    html = FragmentRenderer().render(shell)  # type: ignore[arg-type]
    assert "dz-command" not in html
