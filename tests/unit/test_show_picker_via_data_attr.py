"""Tests for #982 — showPicker via data-attribute, not Alpine on morphable picker.

Background: `_card_picker.html` previously bound `x-show="showPicker"`,
`@click.away="showPicker = false"`, and a stack of `x-transition:*`
attributes on a deep descendant of `<div x-data="dzDashboardBuilder()">`.
On htmx workspace navigation morph, idiomorph re-evaluated those
bindings before Alpine re-established the dzDashboardBuilder scope —
"showPicker is not defined" — fourth ADR-0022 instance after #970,
#972, #978.

Fix per the established pattern:
  - dzDashboardBuilder.init() installs `$watch("showPicker", v => ...)`
    that mirrors the boolean to `data-show-picker="1"|""` on the
    workspace root.
  - CSS reveals `.dz-card-picker` via
    `.dz-workspace[data-show-picker="1"] .dz-card-picker`.
  - Click-outside handling moves to a document-level listener in
    init() (replacing Alpine's `@click.away`).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PICKER = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "workspace" / "_card_picker.html"
DASHBOARD_JS = (
    REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dashboard-builder.js"
)
FRAGMENTS_CSS = (
    REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "css" / "components" / "fragments.css"
)


def test_picker_template_no_x_show_or_click_away() -> None:
    """The `_card_picker.html` div must drop x-show / @click.away / x-transition."""
    html = PICKER.read_text()
    forbidden = (
        'x-show="showPicker"',
        "@click.away=",
        "x-transition:enter=",
        "x-transition:leave=",
    )
    for token in forbidden:
        assert token not in html, (
            f"_card_picker.html still carries `{token}` — re-introduces the "
            f"#982 morph race. Use the data-show-picker / CSS pattern (#982)."
        )


def test_dashboard_builder_watches_show_picker() -> None:
    """dzDashboardBuilder.init() must $watch showPicker and mirror to dataset."""
    js = DASHBOARD_JS.read_text()
    assert '$watch("showPicker"' in js, "dzDashboardBuilder.init() must $watch showPicker (#982)."
    assert "dataset.showPicker" in js, "$watch callback must mirror to `dataset.showPicker` (#982)."


def test_dashboard_builder_has_click_outside_handler() -> None:
    """The Alpine `@click.away` is replaced by a JS document click listener."""
    js = DASHBOARD_JS.read_text()
    # The replacement listener is named _onPickerClickOutside.
    assert "_onPickerClickOutside" in js, (
        "dzDashboardBuilder must install a document-level click-outside "
        "listener (replacing Alpine's `@click.away` which can't survive "
        "a morphable subtree — #982)."
    )
    # Listener must be cleaned up in destroy(). Find the destroy method
    # body specifically (not the prior comment / forward declaration).
    destroy_idx = js.find("destroy() {")
    assert destroy_idx >= 0, "missing destroy() method on dzDashboardBuilder"
    # Walk forward to the matching brace. Crude but adequate — the
    # method body fits comfortably in 3000 chars.
    destroy_block = js[destroy_idx : destroy_idx + 3000]
    # Bound the block at the next `},` at the appropriate nesting.
    assert "_onPickerClickOutside" in destroy_block, (
        "destroy() must remove the click-outside listener to prevent "
        "leaks across workspace re-init (#982)."
    )


def test_css_drives_picker_visibility_off_data_attr() -> None:
    """CSS must show the picker via `[data-show-picker="1"]` selector."""
    css = FRAGMENTS_CSS.read_text()
    assert ".dz-workspace[data-show-picker" in css and ".dz-card-picker" in css, (
        "Missing CSS rule that reveals .dz-card-picker when the ancestor "
        '.dz-workspace[data-show-picker="1"] is set (#982).'
    )
    # Default state must be `display: none` so the picker doesn't flash
    # on initial paint (replaces the prior `x-cloak`-style guard).
    base_idx = css.find(".dz-card-picker {")
    assert base_idx >= 0
    base_block = css[base_idx : css.find("}", base_idx)]
    assert "display: none" in base_block, (
        "Base `.dz-card-picker` rule must set `display: none` (#982)."
    )
