"""Fleet boolean_settings_switch adopt + explicit alt-widget skip (cycle 1783)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_opportunity import scan_appspec

ROOT = Path(__file__).resolve().parents[2]


def _field(name: str, kind: str = "bool") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        type=SimpleNamespace(kind=kind, ref_entity=None),
    )


def test_explicit_toggle_widget_skips_switch_author_action() -> None:
    """mode_press widget=toggle must not thrash boolean_settings_switch residual."""
    entity = SimpleNamespace(
        name="User",
        domain="app",
        fields=[
            _field("name", "str"),
            _field("is_active", "bool"),
            _field("is_starred", "bool"),
        ],
    )
    elements = [
        SimpleNamespace(field_name="is_active", options={"widget": "switch"}),
        SimpleNamespace(field_name="is_starred", options={"widget": "toggle"}),
    ]
    surface = SimpleNamespace(
        name="user_edit",
        entity_ref="User",
        mode=SimpleNamespace(value="edit"),
        sections=[SimpleNamespace(elements=elements)],
        headless=False,
    )
    appspec = SimpleNamespace(
        domain=SimpleNamespace(entities=[entity]),
        surfaces=[surface],
        workspaces=[],
    )
    opps = scan_appspec(appspec)
    switch_rows = [o for o in opps if o.hyperpart == "switch"]
    assert any(o.field == "is_active" and o.status == "emit_covered" for o in switch_rows)
    assert not any(o.field == "is_starred" for o in switch_rows)


def test_simple_task_starred_toggle_not_switch_residual() -> None:
    app = ROOT / "examples" / "simple_task"
    appspec = load_project_appspec(app)
    opps = scan_appspec(appspec)
    starred = [o for o in opps if o.hyperpart == "switch" and o.field == "is_starred"]
    assert not starred, [(o.surface, o.status) for o in starred]
    active = [
        o
        for o in opps
        if o.hyperpart == "switch" and o.field == "is_active" and o.status == "emit_covered"
    ]
    assert active
