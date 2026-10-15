"""Tests for the base DetectionAgent class and @heuristic decorator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.sentinel.agents.base import DetectionAgent, heuristic
from dazzle.sentinel.models import AgentId, Finding, Severity

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec


class _StubAgent(DetectionAgent):
    @property
    def agent_id(self) -> AgentId:
        return AgentId.DI

    @heuristic(heuristic_id="STUB-02", category="test", subcategory="stub", title="Second")
    def check_second(self, appspec: AppSpec) -> list[Finding]:
        return []

    @heuristic(heuristic_id="STUB-01", category="test", subcategory="stub", title="First")
    def check_first(self, appspec: AppSpec) -> list[Finding]:
        return [
            Finding(
                agent=AgentId.DI,
                heuristic_id="STUB-01",
                category="test",
                subcategory="stub",
                severity=Severity.LOW,
                title="Stub finding",
                description="found by stub",
            )
        ]

    def not_a_heuristic(self) -> None:
        pass


class _ErrorAgent(DetectionAgent):
    @property
    def agent_id(self) -> AgentId:
        return AgentId.DI

    @heuristic(heuristic_id="ERR-01", category="test", subcategory="error", title="Explodes")
    def check_explode(self, appspec: AppSpec) -> list[Finding]:
        raise RuntimeError("boom")


def test_get_heuristics_discovers_decorated_methods_sorted_by_id() -> None:
    # check_second is declared first; undecorated methods are not heuristics.
    heuristics = _StubAgent().get_heuristics()
    assert [(m.heuristic_id, m.category, m.title) for m, _ in heuristics] == [
        ("STUB-01", "test", "First"),
        ("STUB-02", "test", "Second"),
    ]
    assert [fn.__name__ for _, fn in heuristics] == ["check_first", "check_second"]


def test_run_counts_heuristics_and_collects_findings(simple_appspec: object) -> None:
    result = _StubAgent().run(simple_appspec)  # type: ignore[arg-type]
    assert result.agent == AgentId.DI
    assert result.heuristics_run == 2
    assert [f.title for f in result.findings] == ["Stub finding"]
    assert result.errors == []
    assert result.duration_ms >= 0


def test_run_captures_heuristic_errors(simple_appspec: object) -> None:
    result = _ErrorAgent().run(simple_appspec)  # type: ignore[arg-type]
    assert result.heuristics_run == 1
    assert len(result.errors) == 1
    assert "boom" in result.errors[0]
    assert result.findings == []
