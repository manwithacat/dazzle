"""simple_task dogfoods form hyperpart emitters (switch + toggle_group)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.qa.hyperpart_opportunity import scan_appspec
from dazzle.render.fragment import FragmentRenderer, SwitchField, ToggleGroupField

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples" / "simple_task"


def test_user_edit_declares_is_active_switch() -> None:
    text = (APP / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "field is_active" in text
    assert "widget=switch" in text
    # Account Status section is the settings-like home
    assert "Account Status" in text


def test_task_forms_declare_priority_toggle_group() -> None:
    text = (APP / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "widget=toggle_group" in text
    assert text.count("field priority") >= 1


def test_simple_task_switch_scenario_emit_covered() -> None:
    appspec = load_project_appspec(APP)
    opps = scan_appspec(appspec)
    switch = [o for o in opps if o.hyperpart == "switch" and o.field == "is_active"]
    assert switch, "expected is_active switch opportunities"
    covered = [o for o in switch if o.status == "emit_covered"]
    assert covered, f"expected emit_covered for widget=switch; got {[o.status for o in switch]}"
    assert any(o.surface == "user_edit" for o in covered)


def test_switch_field_renders_hm_dual_lock_root() -> None:
    html = FragmentRenderer().render(
        SwitchField(name="is_active", label="Active", initial_value="true")
    )
    assert "data-dz-switch" in html
    assert "dz-switch__track" in html


def test_toggle_group_field_renders_hm_dual_lock_root() -> None:
    html = FragmentRenderer().render(
        ToggleGroupField(
            name="priority",
            label="Priority",
            options=(("low", "Low"), ("medium", "Medium"), ("high", "High")),
            initial_value="medium",
        )
    )
    assert "dz-toggle-group" in html
    assert 'type="radio"' in html


def test_dsl_shapes_catalogue_covers_fleet() -> None:
    snap = shapes_snapshot()
    assert snap["count"] >= 80
    assert snap["live"] >= 60
    assert "toggle-group" not in (snap.get("planned_ids") or [])
    assert "switch" not in (snap.get("planned_ids") or [])
