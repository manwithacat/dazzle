"""_build_comparison render — ranked-league region (#1470)."""

from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self, name: str, display: str = "comparison", title: str | None = None) -> None:
        self.name = name
        self.title = title
        self.display = display
        self.empty_message = None


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def _ctx() -> dict:
    return {
        "comparison_rows": [
            {"rank": 1, "label": "North", "value": 100.0, "bar_fraction": 1.0, "outlier": None},
            {"rank": 2, "label": "South", "value": 5.0, "bar_fraction": 0.05, "outlier": "low"},
        ],
        "comparison_max": 100.0,
    }


def test_renders_ranks_labels_values() -> None:
    adapter = WorkspaceRegionAdapter()
    html = _render(adapter.build(_FakeRegion("league", title="League"), _ctx()))
    assert "1. North" in html
    assert "2. South" in html
    assert "100" in html


def test_renders_inline_track_and_outlier_badge() -> None:
    adapter = WorkspaceRegionAdapter()
    html = _render(adapter.build(_FakeRegion("league"), _ctx()))
    # Inline track element (BarTrack progressbar).
    assert "dz-bar-track" in html
    assert 'role="progressbar"' in html
    # Outlier badge on the flagged row.
    assert "⚠" in html
    assert "low" in html


def test_empty_rows_render_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    html = _render(
        adapter.build(_FakeRegion("league"), {"comparison_rows": [], "comparison_max": 0.0})
    )
    assert "No data" in html


def test_non_finite_values_do_not_crash_render() -> None:
    # inf/nan in value or comparison_max would crash BarTrack's _num() — guard it.
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "comparison_rows": [
            {"rank": 1, "label": "Good", "value": 50.0, "bar_fraction": 1.0, "outlier": None},
            {"rank": 2, "label": "Bad", "value": float("inf"), "bar_fraction": 0.5},
            {"rank": 3, "label": "Nan", "value": float("nan"), "bar_fraction": float("nan")},
        ],
        "comparison_max": float("inf"),
    }
    html = _render(adapter.build(_FakeRegion("league"), ctx))
    # Finite row survives; non-finite rows dropped; no crash.
    assert "1. Good" in html
    assert "Bad" not in html and "Nan" not in html


def test_html_escaping_of_label() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "comparison_rows": [
            {
                "rank": 1,
                "label": "<script>alert(1)</script>",
                "value": 10.0,
                "bar_fraction": 1.0,
                "outlier": None,
            },
        ],
        "comparison_max": 10.0,
    }
    html = _render(adapter.build(_FakeRegion("league"), ctx))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
