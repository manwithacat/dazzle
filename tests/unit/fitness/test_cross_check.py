from datetime import UTC, datetime

from dazzle.fitness.cross_check import cross_check_capabilities
from dazzle.fitness.spec_extractor import Capability


class _Story:
    def __init__(self, id: str, title: str, persona: str) -> None:
        self.id = id
        self.title = title
        self.persona = persona


def test_spec_capability_with_no_matching_story_yields_coverage_finding() -> None:
    caps = [Capability(capability="triage incoming ticket", persona="support_agent")]
    stories = [_Story("s1", "close ticket", "support_agent")]

    findings = cross_check_capabilities(
        spec_capabilities=caps,
        stories=stories,
        run_id="r1",
        now=datetime(2026, 4, 13, tzinfo=UTC),
    )
    coverage = [f for f in findings if f.axis == "coverage"]
    assert len(coverage) >= 1
    story_drift = [f for f in coverage if f.locus == "story_drift"]
    assert len(story_drift) == 1
    assert "triage" in story_drift[0].capability_ref


def test_story_with_no_matching_capability_yields_over_impl_finding() -> None:
    caps = [Capability(capability="triage", persona="support_agent")]
    stories = [
        _Story("s1", "triage new ticket", "support_agent"),
        _Story("s2", "export CSV report", "support_agent"),
    ]

    findings = cross_check_capabilities(
        spec_capabilities=caps,
        stories=stories,
        run_id="r1",
        now=datetime(2026, 4, 13, tzinfo=UTC),
    )
    over = [f for f in findings if f.locus == "spec_stale"]
    assert len(over) == 1
    assert "export" in over[0].capability_ref


def test_perfect_match_yields_no_findings() -> None:
    caps = [Capability(capability="triage", persona="agent")]
    stories = [_Story("s1", "triage ticket", "agent")]

    findings = cross_check_capabilities(
        spec_capabilities=caps,
        stories=stories,
        run_id="r1",
        now=datetime(2026, 4, 13, tzinfo=UTC),
    )
    assert findings == []
