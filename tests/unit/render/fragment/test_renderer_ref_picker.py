"""RefPicker → HTML rendering."""

from dazzle.render.fragment import URL, RefPicker
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def test_ref_picker_renders_select_with_data_ref_api() -> None:
    """RefPicker emits a <select> with data-ref-api carrying the URL,
    so dz.filterRefSelect can lazy-fetch options at render time."""
    html = _render(RefPicker(name="assigned_to", label="Assigned", ref_api=URL("/user")))
    assert "<select" in html
    assert 'name="assigned_to"' in html
    assert 'data-ref-api="/user"' in html
    assert "Assigned" in html


def test_ref_picker_renders_initial_selection_as_placeholder_option() -> None:
    """When initial_value is set, render an <option> with that value
    and the initial_label as visible text — so EDIT forms show the
    current selection before the lazy fetch resolves."""
    html = _render(
        RefPicker(
            name="assigned_to",
            label="Assigned",
            ref_api=URL("/user"),
            initial_value="abc-123",
            initial_label="Alice",
        )
    )
    assert 'value="abc-123"' in html
    assert "Alice" in html


def test_ref_picker_required_emits_required_attr() -> None:
    html = _render(RefPicker(name="x", label="X", ref_api=URL("/a"), required=True))
    assert "required" in html


def test_ref_picker_carries_ref_api_for_the_auto_mount() -> None:
    """F4e: dz-utils.js auto-mounts every select[data-ref-api] at load
    and after htmx settles — no per-element x-init."""
    html = _render(RefPicker(name="x", label="X", ref_api=URL("/a")))
    assert 'data-ref-api="/a"' in html
    assert "x-init" not in html


def test_ref_picker_emits_dz_ref_picker_class() -> None:
    """CSS hook for styling — parallels .dz-combobox."""
    html = _render(RefPicker(name="x", label="X", ref_api=URL("/a")))
    assert "dz-ref-picker" in html
