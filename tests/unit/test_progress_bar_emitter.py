"""display: progress_bar hyperpart emitter — unit pins (cycle 1778).

Toned determinate ``.dz-progress`` bar — distinct from StageBar /
``display: progress`` (progress-region).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import FragmentRenderer, ProgressBar, Stack
from dazzle.render.fragment.region._builders_metrics import _BuildersMetricsMixin
from dazzle.render.fragment.region._context import RegionContext

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"


def test_progress_bar_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(ProgressBar(value=62, label="Storage used", tone="success"))
    assert 'class="dz-progress"' in html
    assert 'role="progressbar"' in html
    assert 'aria-label="Storage used"' in html
    assert 'aria-valuenow="62"' in html
    assert 'aria-valuemin="0"' in html
    assert 'aria-valuemax="100"' in html
    assert 'data-dz-tone="success"' in html
    assert 'class="dz-progress__bar"' in html
    assert "--dz-progress-value:62%" in html


def test_progress_bar_clamps_over_max() -> None:
    html = FragmentRenderer().render(ProgressBar(value=150, label="Over", max_value=100))
    assert "--dz-progress-value:100%" in html
    assert 'aria-valuenow="150"' in html


def test_progress_bar_tone_optional() -> None:
    html = FragmentRenderer().render(ProgressBar(value=10, label="Plain"))
    assert "data-dz-tone" not in html


def test_progress_bar_rejects_bad_tone() -> None:
    with pytest.raises(ValueError, match="tone"):
        ProgressBar(value=1, tone="nope")  # type: ignore[arg-type]


def test_progress_bar_rejects_nonpositive_max() -> None:
    with pytest.raises(ValueError, match="max_value"):
        ProgressBar(value=1, max_value=0)


def test_build_progress_bar_from_static_entries() -> None:
    class _A(_BuildersMetricsMixin):
        pass

    region = type(
        "R", (), {"name": "sample_progress", "title": "Capacity", "empty_message": None}
    )()
    ctx: RegionContext = {
        "status_entries": [
            {"title": "Board fill", "body": "62"},
            {"title": "Review lane", "caption": "100", "icon": "success"},
            {"title": "Urgent", "body": "38%", "icon": "warning"},
        ],
        "items": [],
        "empty_message": "none",
    }
    surface = _A()._build_progress_bar(region, ctx)
    html = FragmentRenderer().render(surface)
    assert html.count('class="dz-progress"') == 3
    assert 'aria-label="Board fill"' in html
    assert 'aria-label="Review lane"' in html
    assert 'data-dz-tone="success"' in html
    assert 'data-dz-tone="warning"' in html
    assert "--dz-progress-value:62%" in html
    assert "--dz-progress-value:100%" in html


def test_build_progress_bar_from_item_percent() -> None:
    class _A(_BuildersMetricsMixin):
        pass

    region = type("R", (), {"name": "caps", "title": "Caps", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {"name": "CPU", "percent": 45, "tone": "warning"},
            {"title": "Disk", "progress": 80},
        ],
        "status_entries": [],
    }
    surface = _A()._build_progress_bar(region, ctx)
    html = FragmentRenderer().render(surface)
    assert html.count('class="dz-progress"') == 2
    assert 'aria-label="CPU"' in html
    assert 'aria-label="Disk"' in html
    assert "--dz-progress-value:45%" in html


def test_build_progress_bar_empty_state() -> None:
    class _A(_BuildersMetricsMixin):
        pass

    region = type("R", (), {"name": "empty", "title": "Empty", "empty_message": "No bars"})()
    ctx: RegionContext = {"items": [], "status_entries": [], "empty_message": "No bars"}
    surface = _A()._build_progress_bar(region, ctx)
    html = FragmentRenderer().render(surface)
    assert "No progress" in html or "No bars" in html
    assert 'class="dz-progress"' not in html


def test_stack_of_progress_bars() -> None:
    html = FragmentRenderer().render(
        Stack(
            children=(
                ProgressBar(value=10, label="A"),
                ProgressBar(value=90, label="B", tone="destructive"),
            ),
            gap="sm",
        )
    )
    assert html.count('class="dz-progress"') == 2
    assert 'data-dz-tone="destructive"' in html


def test_simple_task_declares_sample_progress() -> None:
    text = (SIMPLE / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "sample_progress:" in text
    assert "display: progress_bar" in text
    assert "Board fill" in text


def test_simple_task_appspec_sample_progress_region() -> None:
    appspec = load_project_appspec(SIMPLE)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    found = False
    for ws in workspaces:
        for region in list(getattr(ws, "regions", None) or []):
            if getattr(region, "name", None) == "sample_progress":
                found = True
                display = getattr(region, "display", None)
                assert (
                    str(display) in ("progress_bar", "DisplayMode.PROGRESS_BAR")
                    or getattr(display, "value", None) == "progress_bar"
                )
    assert found, "sample_progress region missing from simple_task appspec"


def test_progress_shape_live() -> None:
    snap = shapes_snapshot()
    assert "progress" not in snap["planned_ids"]
    assert snap["next_planned"] != "progress"
