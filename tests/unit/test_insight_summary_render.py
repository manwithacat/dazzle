from dazzle.render.fragment.insight import InsightNarrative
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self) -> None:
        self.name = "ins"
        self.title = "Team Insight"
        self.display = "insight_summary"
        self.empty_message = None


def _render(ctx: dict) -> str:
    return FragmentRenderer().render(WorkspaceRegionAdapter().build(_FakeRegion(), ctx))


def test_renders_narrative_and_trust_block() -> None:
    nar = InsightNarrative(
        lines=("52 alerts across 6 teams.", "Platform is highest at 12 (23% of the total)."),
        citations=(("Platform", 12.0), ("ML", 1.0)),
        scope="across all teams",
        badge="Computed from live data",
    )
    html = _render({"insight_narrative": nar})
    assert "Platform is highest at 12" in html
    assert "across all teams" in html
    assert "Computed from live data" in html
    assert "Platform" in html and "12" in html  # citation values present


def test_empty_narrative_degrades() -> None:
    nar = InsightNarrative(lines=("No data to summarise.",), citations=(), scope="across all teams")
    html = _render({"insight_narrative": nar})
    assert "No data to summarise." in html


def test_html_escaping_of_labels() -> None:
    nar = InsightNarrative(
        lines=("<script>alert(1)</script> is highest at 9.",),
        citations=(("<script>x</script>", 9.0),),
        scope="across all teams",
    )
    html = _render({"insight_narrative": nar})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
