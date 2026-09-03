"""Map empty must not dump generic 'No locations.' (oral #228)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_map_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_metrics import _BuildersMetricsMixin

FIELDTEST = Path("examples/fieldtest_hub")
FIELDTEST_DSL = FIELDTEST / "dsl" / "app.dsl"


class _A(_BuildersMetricsMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "device_map",
        "title": "Device map",
        "empty_message": None,
        "source": "Device",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_map(region: object, ctx: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {"items": [], "status_entries": []}
    payload.update(ctx or {})
    return FragmentRenderer().render(_A()._build_map(region, payload))


def test_fieldtest_device_map_is_live() -> None:
    block = FIELDTEST_DSL.read_text()
    region = block.split("  device_map:", 1)[1].split("  ux:", 1)[0]
    assert "display: map" in region
    assert "source: Device" in region
    assert 'empty: "No devices registered"' in region


def test_clerk_empty_map_title_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    device = next(e for e in spec.domain.entities if e.name == "Device")
    assert device.title == "Device"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Device", labels) == "Device"
    assert clerk_entity_confirm_noun("Device", labels) == "device"
    assert clerk_empty_map_title("Device", labels) == "No devices on this map."
    assert clerk_empty_map_title("Device") == "No devices on this map."


def test_clerk_empty_map_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_map_title(junk) == "No locations."


def test_fieldtest_issue_report_map_is_issue_reports() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_map_title("IssueReport", labels) == "No issue reports on this map."


def test_map_empty_is_devices_not_no_locations() -> None:
    html = _render_map(_region())
    assert "dz-empty-dense" in html
    assert "No devices on this map." in html
    assert "No locations." not in html
    assert "No devicess" not in html


def test_map_empty_ctx_source_entity_still_splits() -> None:
    html = _render_map(_region(source=""), {"source_entity": "Device"})
    assert "No devices on this map." in html
    assert "No locations." not in html


def test_map_empty_missing_entity_stays_no_locations() -> None:
    html = _render_map(_region(source=""))
    assert "No locations." in html
    assert "No devices" not in html


def test_map_empty_leftover_invents_no_collection() -> None:
    html = _render_map(_region(source="zzz"))
    assert "No locations." in html
    assert "No zzz" not in html


def test_map_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_map(_region(source="Device"), {"entity_name": "Item"})
    assert "No devices on this map." in html
    assert "No locations." not in html


def test_map_authored_empty_still_wins() -> None:
    html = _render_map(_region(empty_message="No devices registered"))
    assert "No devices registered" in html
    assert "No locations." not in html
    assert "No devices on this map." not in html


def test_map_populated_still_renders_pins() -> None:
    html = _render_map(
        _region(),
        {
            "items": [{"id": "d1", "name": "Probe-01", "status": "active"}],
        },
    )
    assert "Probe-01" in html
    assert "No locations." not in html
    assert "No devices on this map." not in html
