"""Pivot must not leak dimension keys as measure columns (oral #160)."""

from __future__ import annotations

from dazzle.render.filters import clerk_pivot_measure_display, clerk_pivot_measure_keys
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakePivot:
    name = "alert_pivot"
    title = "Alert pivot"
    display = "pivot_table"
    empty_message = "No alerts to pivot"


def test_clerk_pivot_measure_keys_drops_dims_and_labels() -> None:
    keys = clerk_pivot_measure_keys(
        ["system", "system_label", "severity", "count", "zzz"],
        [{"name": "system", "is_fk": True}, {"name": "severity"}],
    )
    assert keys == ("count", "zzz")


def test_clerk_pivot_measure_display_whole_count_and_leftover() -> None:
    assert clerk_pivot_measure_display(12.0) == "12"
    assert clerk_pivot_measure_display(12) == "12"
    assert clerk_pivot_measure_display(0) == "0"
    assert clerk_pivot_measure_display(12.5) == "12.5"
    assert clerk_pivot_measure_display("zzz") == "zzz"
    assert clerk_pivot_measure_display("1e2") == "1e2"
    assert clerk_pivot_measure_display(None) == "—"


def test_pivot_html_does_not_leak_dim_keys_as_measures() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakePivot(),
            {
                "pivot_dim_specs": [
                    {"name": "system", "label": "System", "is_fk": True},
                    {"name": "severity", "label": "Severity", "is_fk": False},
                ],
                "pivot_buckets": [
                    {
                        "system": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "system_label": "Auth",
                        "severity": "critical",
                        "count": 12.0,
                        "zzz": "zzz",
                    },
                    {
                        "system": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "system_label": "Billing",
                        "severity": "warning",
                        "count": 4,
                        "zzz": "zzz",
                    },
                ],
            },
        )
    )
    assert "System" in html
    assert "Severity" in html
    assert ">Count<" in html
    assert "12" in html
    assert "12.0" not in html
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in html
    assert "System Label" not in html
    assert html.count("is-measure") >= 4  # 2 header+cell pairs for count + leftover zzz
    assert "zzz" in html
    assert "Auth" in html


def test_pivot_html_renders_every_measure_column() -> None:
    """#1800: a multi-measure pivot (avg + derived percentage) renders one
    header and one cell per measure, decimals intact."""
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakePivot(),
            {
                "pivot_dim_specs": [
                    {"name": "question", "label": "Question", "is_fk": False},
                    {"name": "klass", "label": "Klass", "is_fk": False},
                ],
                "pivot_buckets": [
                    {"question": "Q1", "klass": "7A", "avg_score": 7.25, "facility_pct": 62.5},
                ],
            },
        )
    )
    assert ">Avg Score<" in html
    assert ">Facility Pct<" in html
    assert "7.25" in html
    assert "62.5" in html
    assert html.count("is-measure") == 4  # two measure headers + two cells
