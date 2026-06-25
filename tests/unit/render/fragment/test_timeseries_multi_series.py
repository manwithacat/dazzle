"""Multi-series TimeSeries rendering (#1473).

Covers the renderer tail: a `TimeSeries` carrying `series` emits the
overlaid multi-series SVG plus a legend naming each series.
"""

from dazzle.render.fragment import TimeSeries, TimeSeriesSeries
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self, name: str, display: str, title: str | None = None) -> None:
        self.name = name
        self.display = display
        self.title = title
        self.empty_message = None


def _render(t: TimeSeries) -> str:
    return FragmentRenderer().render(t)


def _build_html(display: str, ctx: dict) -> str:
    node = WorkspaceRegionAdapter().build(_FakeRegion("r", display=display), ctx)
    return FragmentRenderer().render(node)


def test_multi_series_timeseries_emits_overlaid_svg() -> None:
    t = TimeSeries(
        label="Alerts by severity",
        view="area",
        series=(
            TimeSeriesSeries(name="high", points=(("W1", 2.0), ("W2", 3.0))),
            TimeSeriesSeries(name="low", points=(("W1", 1.0), ("W2", 4.0))),
        ),
    )
    html = _render(t)
    assert "dz-area-chart-region" in html
    assert html.count("<polyline ") == 2  # one line per series
    assert "<title>high · W1: 2</title>" in html


def test_multi_series_timeseries_emits_legend_with_series_names() -> None:
    t = TimeSeries(
        label="Alerts by severity",
        view="area",
        series=(
            TimeSeriesSeries(name="high", points=(("W1", 2.0),)),
            TimeSeriesSeries(name="low", points=(("W1", 1.0),)),
        ),
    )
    html = _render(t)
    assert "dz-chart-legend" in html
    assert ">high<" in html and ">low<" in html


def test_single_series_timeseries_still_renders_without_legend() -> None:
    t = TimeSeries(label="Revenue", points=(("Jan", 10.0), ("Feb", 20.0)), view="line")
    html = _render(t)
    assert "dz-line-chart-region" in html
    assert "dz-chart-legend" not in html
    assert html.count("<polyline ") == 1


# === builder: ctx["series"] → multi-series TimeSeries (#1473) ===


def test_builder_area_chart_with_series_renders_overlaid() -> None:
    html = _build_html(
        "area_chart",
        {
            "series": [
                {
                    "name": "high",
                    "points": [{"label": "W1", "value": 2}, {"label": "W2", "value": 3}],
                },
                {
                    "name": "low",
                    "points": [{"label": "W1", "value": 1}, {"label": "W2", "value": 4}],
                },
            ],
        },
    )
    assert "dz-area-chart-region" in html
    assert html.count("<polyline ") == 2
    assert "dz-chart-legend" in html


def test_builder_area_chart_without_series_uses_points() -> None:
    html = _build_html(
        "area_chart",
        {"points": [{"label": "W1", "value": 2}, {"label": "W2", "value": 3}]},
    )
    assert "dz-area-chart-region" in html
    assert html.count("<polyline ") == 1
    assert "dz-chart-legend" not in html
