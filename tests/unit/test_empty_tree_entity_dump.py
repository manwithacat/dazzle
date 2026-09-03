"""Tree empty must not dump generic 'No items' (oral #224)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_tree_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_misc import _BuildersMiscMixin

FIELDTEST = Path("examples/fieldtest_hub")
HR = Path("examples/hr_records")
FIELDTEST_DSL = FIELDTEST / "dsl" / "app.dsl"


class _A(_BuildersMiscMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "device_tree",
        "title": "Device tree",
        "empty_message": None,
        "source": "Device",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_tree(region: object, ctx: dict[str, object] | None = None) -> str:
    return FragmentRenderer().render(_A()._build_tree(region, ctx or {}))


def test_fieldtest_device_tree_is_live() -> None:
    block = FIELDTEST_DSL.read_text()
    region = block.split("  device_tree:", 1)[1].split("  fleet_diagram:", 1)[0]
    assert "display: tree" in region
    assert "source: Device" in region
    assert "group_by: batch_number" in region


def test_clerk_empty_tree_title_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    device = next(e for e in spec.domain.entities if e.name == "Device")
    assert device.title == "Device"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Device", labels) == "Device"
    assert clerk_entity_confirm_noun("Device", labels) == "device"
    assert clerk_empty_tree_title("Device", labels) == "No devices"
    assert clerk_empty_tree_title("Device") == "No devices"


def test_clerk_empty_tree_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_tree_title(junk) == "No items"


def test_hr_department_tree_is_departments() -> None:
    spec = load_project(HR)
    dept = next(e for e in spec.domain.entities if e.name == "Department")
    assert dept.title == "Department"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_tree_title("Department", labels) == "No departments"


def test_tree_empty_is_devices_not_no_items() -> None:
    html = _render_tree(_region())
    assert "No devices" in html
    assert ">No items<" not in html
    assert "No devicess" not in html


def test_tree_empty_ctx_source_entity_still_splits() -> None:
    html = _render_tree(_region(source=""), {"source_entity": "Device"})
    assert "No devices" in html
    assert ">No items<" not in html


def test_tree_empty_missing_entity_stays_no_items() -> None:
    html = _render_tree(_region(source=""))
    assert ">No items<" in html
    assert "No devices" not in html


def test_tree_empty_leftover_invents_no_collection() -> None:
    html = _render_tree(_region(source="zzz"))
    assert ">No items<" in html
    assert "No zzz" not in html


def test_tree_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_tree(_region(source="Device"), {"entity_name": "Item"})
    assert "No devices" in html
    assert ">No items<" not in html


def test_tree_populated_still_renders_nodes() -> None:
    html = _render_tree(
        _region(),
        {
            "items": [
                {
                    "name": "B-2026-01",
                    "_group": True,
                    "children": [{"id": "d1", "name": "FT-PROBE-A12"}],
                }
            ]
        },
    )
    assert "B-2026-01" in html
    assert "FT-PROBE-A12" in html
    assert ">No items<" not in html
    assert "No devices" not in html
