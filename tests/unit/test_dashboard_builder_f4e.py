"""Tier F4e — the dzDashboardBuilder Alpine island converts to a vanilla
factory (`createDzDashboardBuilder` in dashboard-builder.js, mounted per
`[data-dz-dashboard-builder]` root at load + after htmx settles).

These pins hold the emitter side of the contract: no Alpine bindings
anywhere in the workspace shell; the toolbar's save-state spans are
CSS-driven off the button's `data-dz-save-state`; the reset/save/
add-card triggers carry `data-dz-action` for the controller's root
delegation.
"""

from __future__ import annotations

from dazzle.render.fragment import FragmentRenderer, WorkspaceShell, WorkspaceToolbar

_R = FragmentRenderer()


def _shell_html() -> str:
    from dazzle.render.fragment import Text

    return _R.render(WorkspaceShell(workspace_name="ops", title="Ops", body=Text(body="x")))


def test_workspace_root_carries_the_controller_marker() -> None:
    html = _shell_html()
    assert "data-dz-dashboard-builder" in html
    assert "x-data" not in html


def test_toolbar_is_state_in_dom() -> None:
    html = _R.render(WorkspaceToolbar())
    assert "x-data" not in html and "x-show" not in html and "x-cloak" not in html
    assert "@click" not in html and ":disabled" not in html
    # triggers for the controller's root delegation
    assert 'data-dz-action="reset"' in html
    assert 'data-dz-action="save"' in html
    # save button SSRs the clean state, disabled; spans key off it
    assert 'data-dz-save-state="clean"' in html
    assert "disabled" in html
    for state in ("clean", "dirty", "saving", "saved", "error"):
        assert f'data-dz-when="{state}"' in html


def test_add_card_trigger_uses_action_delegation() -> None:
    from dazzle.render.fragment import AddCardRow, CardPicker

    html = _R.render(AddCardRow(picker=CardPicker(entries=(), catalog_json="[]")))
    assert 'data-dz-action="toggle-picker"' in html
    assert "@click" not in html
    assert 'data-test-id="dz-add-card-trigger"' in html


def test_picker_entries_use_add_region_delegation() -> None:
    from dazzle.render.fragment import CardPicker, CardPickerEntry

    picker = CardPicker(
        entries=(CardPickerEntry(name="alerts", title="Alerts", entity="Alert", display="list"),),
        catalog_json="[]",
    )
    html = _R.render(picker)
    assert 'data-dz-add-region="alerts"' in html
    assert "@click" not in html
