"""HaTchi-MaXchi tranche 1 — bundle carries the new component contracts."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

STATIC = Path(__file__).parents[2] / "src" / "dazzle" / "page" / "runtime" / "static"


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
    js = (STATIC / "js" / "dz-confirm.js").read_text()
    assert "htmx:confirm" in js
    assert "issueRequest(true)" in js
    assert "data-dz-native-confirm" in js  # opt-out contract
    # user-controlled question must go through textContent, never innerHTML
    assert 'querySelector(".dz-alert-dialog__message").textContent' in js


def test_empty_state_title_uses_text_token() -> None:
    css = (STATIC / "css" / "components" / "fragment-primitives.css").read_text()
    assert ".dz-empty-state__title {\n  color: var(--colour-text);" in css
