from dazzle.render.fragment.insight import InsightNarrative, StoredInsight
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


_DET = InsightNarrative(
    lines=("52 alerts across 6 teams.", "Platform is highest at 12 (23% of the total)."),
    citations=(("Platform", 12.0), ("ML", 1.0)),
    scope="across all teams",
)


def test_stored_overlay_with_grounding_and_confidence() -> None:
    stored = StoredInsight(
        prose=("Alert volume is concentrated in Platform; ML is unusually quiet.",),
        confidence="medium",
        generated_at="2026-06-25 14:00",
    )
    html = _render({"insight_narrative": _DET, "stored_insight": stored})
    assert "unusually quiet" in html  # the stored prose
    assert "Platform" in html and "12" in html  # the deterministic citations (grounding) beneath
    assert "medium" in html  # confidence
    assert "2026-06-25 14:00" in html  # as-of freshness
    assert 'data-dz-tone="warning"' in html  # medium -> warning tone


def test_fallback_to_deterministic_when_no_stored() -> None:
    html = _render({"insight_narrative": _DET, "stored_insight": None})
    assert "Platform is highest at 12" in html  # deterministic prose
    assert "Computed from live data" in html  # deterministic badge
    assert 'data-dz-tone="warning"' not in html  # no confidence badge


def test_stored_prose_escaped() -> None:
    stored = StoredInsight(
        prose=("<script>alert(1)</script>",), confidence="high", generated_at="t"
    )
    html = _render({"insight_narrative": _DET, "stored_insight": stored})
    assert "<script>alert(1)</script>" not in html
