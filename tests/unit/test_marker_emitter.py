"""marker + display:map hyperpart emitter — unit pins (cycle 1766).

``display: map`` → ``MapBoard`` of ``Marker`` / ``.dz-marker`` pin chrome.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import FragmentRenderer, MapBoard, Marker
from dazzle.render.fragment.region._builders_metrics import _BuildersMetricsMixin
from dazzle.render.fragment.region._context import RegionContext

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"
FIELDTEST = ROOT / "examples" / "fieldtest_hub"


def test_marker_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        Marker(label="HQ", tone="success", size="lg", x_pct=30.0, y_pct=40.0, title="Head office")
    )
    assert 'class="dz-marker"' in html
    assert "data-dz-marker" in html
    assert 'data-dz-tone="success"' in html
    assert 'data-dz-size="lg"' in html
    assert 'class="dz-marker__pin"' in html
    assert 'class="dz-marker__label"' in html
    assert "HQ" in html
    assert "Head office" in html
    assert "left:30.00%" in html


def test_map_board_emits_canvas_and_pins() -> None:
    html = FragmentRenderer().render(
        MapBoard(
            markers=(
                Marker(label="HQ", tone="success", x_pct=20.0, y_pct=30.0),
                Marker(label="Depot", tone="warning", x_pct=70.0, y_pct=60.0),
            ),
            label="Sites",
        )
    )
    assert 'class="dz-map"' in html
    assert "data-dz-map" in html
    assert 'data-dz-entry-count="2"' in html
    assert 'class="dz-map__canvas"' in html
    assert html.count('class="dz-marker"') == 2
    assert "HQ" in html
    assert "Depot" in html


def test_map_board_empty_state() -> None:
    html = FragmentRenderer().render(MapBoard(markers=(), empty_message="No pins"))
    assert "No pins" in html
    assert 'data-dz-entry-count="0"' in html


def test_build_map_from_static_entries() -> None:
    class _A(_BuildersMetricsMixin):
        pass

    region = type("R", (), {"name": "sample_map", "title": "Sites", "empty_message": None})()
    ctx: RegionContext = {
        "status_entries": [
            {"title": "HQ", "body": "success"},
            {"title": "Alert", "caption": "danger"},
        ],
        "items": [],
        "empty_message": "none",
    }
    surface = _A()._build_map(region, ctx)
    html = FragmentRenderer().render(surface)
    assert 'class="dz-map"' in html
    assert "data-dz-marker" in html
    assert "HQ" in html
    assert "Alert" in html


def test_build_map_from_device_like_items() -> None:
    class _A(_BuildersMetricsMixin):
        pass

    region = type("R", (), {"name": "device_map", "title": "Devices", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {"id": "d1", "name": "Unit A", "location": "Berlin", "status": "active"},
            {"id": "d2", "name": "Unit B", "location": "Paris", "status": "recalled"},
        ],
        "status_entries": [],
    }
    surface = _A()._build_map(region, ctx)
    html = FragmentRenderer().render(surface)
    assert "Berlin" in html
    assert "Paris" in html
    assert 'data-dz-tone="success"' in html
    assert 'data-dz-tone="danger"' in html
    assert 'data-dz-entry-count="2"' in html


def test_simple_task_declares_sample_map() -> None:
    text = (SIMPLE / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "sample_map:" in text
    assert "display: map" in text
    assert "HQ" in text


def test_simple_task_appspec_sample_map_region() -> None:
    appspec = load_project_appspec(SIMPLE)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    admin = next((w for w in workspaces if getattr(w, "name", None) == "admin_dashboard"), None)
    assert admin is not None
    regions = list(getattr(admin, "regions", None) or [])
    by_name = {getattr(r, "name", None): r for r in regions}
    region = by_name.get("sample_map")
    assert region is not None, f"sample_map missing; regions={list(by_name)}"
    display = getattr(region, "display", None)
    display_v = getattr(display, "value", display)
    assert display_v == "map"


def test_fieldtest_declares_device_map() -> None:
    text = (FIELDTEST / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "device_map:" in text
    assert "display: map" in text


def test_marker_shape_live() -> None:
    snap = shapes_snapshot()
    assert "marker" not in snap["planned_ids"]
    assert snap["next_planned"] != "marker"
