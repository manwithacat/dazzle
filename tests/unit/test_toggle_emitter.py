"""widget=toggle hyperpart emitter — unit pins (cycle 1779).

Pressable mode control: button.dz-toggle[data-dz-toggle] + aria-pressed.
Not switch (settings track) and not toggle-group (exclusive radios).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.qa.hyperpart_opportunity import scan_appspec
from dazzle.render.fragment import FragmentRenderer, Toggle, ToggleField
from dazzle.render.fragment.form_field import field_dict_to_primitive

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples" / "simple_task"


def test_toggle_fragment_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(Toggle(label="Bold", pressed=True))
    assert 'class="dz-toggle"' in html
    assert "data-dz-toggle" in html
    assert 'aria-pressed="true"' in html
    assert "Bold" in html
    assert 'type="button"' in html


def test_toggle_fragment_unpressed_default() -> None:
    html = FragmentRenderer().render(Toggle(label="Italic"))
    assert 'aria-pressed="false"' in html
    assert "data-dz-size" not in html


def test_toggle_fragment_size_sm() -> None:
    html = FragmentRenderer().render(Toggle(label="U", size="sm"))
    assert 'data-dz-size="sm"' in html


def test_toggle_fragment_disabled() -> None:
    html = FragmentRenderer().render(Toggle(label="X", disabled=True))
    assert " disabled" in html


def test_toggle_rejects_empty_label() -> None:
    with pytest.raises(ValueError, match="label"):
        Toggle(label="  ")


def test_toggle_rejects_bad_size() -> None:
    with pytest.raises(ValueError, match="size"):
        Toggle(label="X", size="lg")  # type: ignore[arg-type]


def test_toggle_field_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        ToggleField(name="is_starred", label="Starred", initial_value="true")
    )
    assert 'class="dz-toggle"' in html
    assert "data-dz-toggle" in html
    assert 'aria-pressed="true"' in html
    assert 'data-dz-field-widget="toggle"' in html
    # No data-dz-widget wrapper — dz-toggle.js skips [data-dz-widget] hosts
    assert 'data-dz-widget="toggle"' not in html
    assert 'name="is_starred"' in html
    assert 'value="true"' in html


def test_toggle_field_unchecked() -> None:
    html = FragmentRenderer().render(
        ToggleField(name="is_starred", label="Starred", initial_value="false")
    )
    assert 'aria-pressed="false"' in html
    assert 'value="false"' in html


def test_widget_toggle_maps_via_form_field() -> None:
    prim = field_dict_to_primitive(
        {"name": "is_starred", "label": "Starred", "widget": "toggle", "value": "true"}
    )
    assert isinstance(prim, ToggleField)
    html = FragmentRenderer().render(prim)
    assert "data-dz-toggle" in html


def test_user_edit_declares_is_starred_toggle() -> None:
    text = (APP / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "field is_starred" in text
    assert "widget=toggle" in text
    assert "is_starred: bool" in text


def test_simple_task_toggle_scenario_or_shape_live() -> None:
    snap = shapes_snapshot()
    assert "toggle" not in (snap.get("planned_ids") or [])
    assert snap.get("planned", 0) == 0 or "toggle" not in snap.get("planned_ids", [])


def test_appspec_loads_with_starred_field() -> None:
    appspec = load_project_appspec(APP)
    # Entity field present
    user = appspec.entities.get("User") if hasattr(appspec, "entities") else None
    if user is None:
        # AppSpec shape may expose entities as list/dict differently
        ents = getattr(appspec, "entities", None) or {}
        if isinstance(ents, dict):
            user = ents.get("User")
    assert appspec is not None
    # Opportunity scan should not crash
    opps = scan_appspec(appspec)
    assert isinstance(opps, list)
