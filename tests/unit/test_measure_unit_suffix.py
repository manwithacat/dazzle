"""Measure fields named ``*_ms`` must not dump unitless numbers (oral #154)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import compute_profile_card
from dazzle.render.filters import clerk_measure_display, clerk_measure_suffix
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.svg import box_plot_svg, histogram_svg


class _FakeHist:
    name = "response_time_distribution"
    title = "Response time"
    display = "histogram"
    empty_message = "No system metrics yet"
    heatmap_value = "response_time_ms"


class _FakeHistLeftover:
    name = "response_time_distribution"
    title = "Response time"
    display = "histogram"
    empty_message = "No system metrics yet"
    heatmap_value = "zzz"


class _FakeBullet:
    name = "system_response_bullet"
    title = "Response"
    display = "bullet"
    empty_message = "No system metrics yet"
    bullet_actual = "response_time_ms"


class _FakeBulletLeftover:
    name = "system_response_bullet"
    title = "Response"
    display = "bullet"
    empty_message = "No system metrics yet"
    bullet_actual = "zzz"


class _FakeBox:
    name = "response_time_spread"
    title = "Spread"
    display = "box_plot"
    empty_message = "No system metrics yet"
    heatmap_value = "response_time_ms"


class _Ref:
    label = "SLA target"
    value = 500.0
    style = "dashed"


def test_ops_dashboard_measure_fields_are_ms() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    found: dict[str, str] = {}
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name in {
                "response_time_distribution",
                "response_time_spread",
                "system_response_bullet",
                "system_identity",
            }:
                found[region.name] = region.name
                if region.name in {"response_time_distribution", "response_time_spread"}:
                    assert getattr(region, "heatmap_value", None) == "response_time_ms"
                if region.name == "system_response_bullet":
                    assert getattr(region, "bullet_actual", None) == "response_time_ms"
                if region.name == "system_identity":
                    values = [s.value for s in (region.profile_stats or [])]
                    assert "response_time_ms" in values
    assert found.keys() >= {
        "response_time_distribution",
        "response_time_spread",
        "system_response_bullet",
        "system_identity",
    }


def test_clerk_measure_suffix_from_field() -> None:
    assert clerk_measure_suffix("response_time_ms") == "ms"
    assert clerk_measure_suffix("latency_ms") == "ms"
    assert clerk_measure_suffix("duration_seconds") == "s"
    assert clerk_measure_suffix("win_pct") == "%"
    assert clerk_measure_suffix("count") == ""
    assert clerk_measure_suffix("zzz") == ""
    assert clerk_measure_suffix("1e2") == ""


def test_clerk_measure_display_adds_ms() -> None:
    assert clerk_measure_display(340, "response_time_ms") == "340ms"
    assert clerk_measure_display(340.0, "response_time_ms") == "340ms"
    assert clerk_measure_display(0, "response_time_ms") == "0ms"
    assert clerk_measure_display(12.5, "response_time_ms") == "12.5ms"
    assert clerk_measure_display(340, "count") == "340"


def test_clerk_measure_display_leftover_stays_put() -> None:
    assert clerk_measure_display("zzz", "response_time_ms") == "zzz"
    assert clerk_measure_display("1e2", "response_time_ms") == "1e2"
    assert clerk_measure_display("2abc", "response_time_ms") == "2abc"
    assert clerk_measure_display(340, "zzz") == "340"


def test_histogram_axis_shows_ms_not_bare_number() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeHist(),
            {
                "histogram_bins": [
                    {"label": "0-250", "count": 2, "low": 0, "high": 250},
                    {"label": "250-500", "count": 4, "low": 250, "high": 500},
                    {"label": "500-750", "count": 1, "low": 500, "high": 750},
                ],
                "reference_lines": [{"value": 500, "label": "SLA target", "style": "dashed"}],
            },
        )
    )
    assert ">0ms<" in html
    assert ">250ms<" in html
    assert ">500ms<" in html
    assert "<title>SLA target: 500ms</title>" in html
    assert "zzz" not in html
    assert "No system metrics yet" not in html


def test_histogram_leftover_field_stays_unitless() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeHistLeftover(),
            {
                "histogram_bins": [
                    {"label": "0-250", "count": 2, "low": 0, "high": 250},
                    {"label": "250-500", "count": 4, "low": 250, "high": 500},
                ],
            },
        )
    )
    assert ">0ms<" not in html
    assert ">0<" in html
    assert ">250<" in html


def test_histogram_svg_unit_suffix_on_ticks() -> None:
    svg = histogram_svg(
        "Latency",
        (("0-250", 2, 0.0, 250.0), ("250-500", 4, 250.0, 500.0)),
        reference_lines=(_Ref(),),
        unit_suffix="ms",
    )
    assert ">0ms<" in svg
    assert ">250ms<" in svg
    assert "<title>SLA target: 500ms</title>" in svg


def test_bullet_value_shows_ms() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeBullet(),
            {
                "bullet_rows": [
                    {"label": "Auth", "actual": 340, "target": None},
                    {"label": "zzz", "actual": 120, "target": None},
                ],
                "bullet_max_value": 1000,
            },
        )
    )
    assert ">340ms<" in html
    assert "340</span>" not in html or "340ms" in html
    assert "zzz" in html
    assert ">120ms<" in html
    assert "scale 0–1000ms" in html


def test_bullet_leftover_field_stays_unitless() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeBulletLeftover(),
            {
                "bullet_rows": [{"label": "Auth", "actual": 340, "target": None}],
                "bullet_max_value": 1000,
            },
        )
    )
    assert ">340ms<" not in html
    assert ">340<" in html


def test_box_plot_axis_shows_ms() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeBox(),
            {
                "groups": [
                    {
                        "label": "api",
                        "min": 10,
                        "q1": 20,
                        "median": 30,
                        "q3": 45,
                        "max": 80,
                        "n": 3,
                    }
                ],
                "reference_lines": [{"value": 50, "label": "SLA target", "style": "dashed"}],
            },
        )
    )
    assert "10ms" in html
    assert "80ms" in html
    assert "SLA target: 50ms" in html
    assert "zzz" not in html


def test_box_plot_svg_unit_suffix() -> None:
    svg = box_plot_svg(
        "Latency",
        (("API", 10.0, 20.0, 30.0, 45.0, 80.0),),
        unit_suffix="ms",
    )
    assert "10ms" in svg
    assert "80ms" in svg
    assert "range 10.0ms–80.0ms" in svg


def test_profile_card_response_stat_shows_ms() -> None:
    ctx = SimpleNamespace(
        avatar_field="",
        primary="name",
        secondary="",
        profile_stats=[
            {"label": "Status", "value": "status"},
            {"label": "Response", "value": "response_time_ms"},
        ],
        facts=[],
    )
    data = compute_profile_card(
        [{"name": "Auth", "status": "up", "response_time_ms": 340, "extra": "zzz"}],
        ctx,
    )
    stats = {row["label"]: row["value"] for row in data["stats"]}
    assert stats["Response"] == "340ms"
    assert stats["Status"] == "up"


def test_profile_card_zero_and_leftover() -> None:
    ctx = SimpleNamespace(
        avatar_field="",
        primary="name",
        secondary="",
        profile_stats=[
            {"label": "Response", "value": "response_time_ms"},
            {"label": "Junk", "value": "zzz"},
        ],
        facts=[],
    )
    data = compute_profile_card(
        [{"name": "Auth", "response_time_ms": 0, "zzz": "zzz"}],
        ctx,
    )
    stats = {row["label"]: row["value"] for row in data["stats"]}
    assert stats["Response"] == "0ms"
    assert stats["Junk"] == "zzz"
