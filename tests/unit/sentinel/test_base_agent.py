"""Tests for the base DetectionAgent class and @heuristic decorator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.sentinel.agents.base import DetectionAgent, HeuristicMeta, heuristic
from dazzle.sentinel.models import AgentId, AgentResult, Finding, Severity

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec


# =============================================================================
# Fixtures — minimal concrete agent
# =============================================================================


class _StubAgent(DetectionAgent):
    @property
    def agent_id(self) -> AgentId:
        return AgentId.DI

    @heuristic(
        heuristic_id="STUB-01",
        category="test",
        subcategory="stub",
        title="First heuristic",
    )
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

    @heuristic(
        heuristic_id="STUB-02",
        category="test",
        subcategory="stub",
        title="Second heuristic",
    )
    def check_second(self, appspec: AppSpec) -> list[Finding]:
        return []

    def not_a_heuristic(self) -> None:
        pass


class _ErrorAgent(DetectionAgent):
    @property
    def agent_id(self) -> AgentId:
        return AgentId.DI

    @heuristic(
        heuristic_id="ERR-01",
        category="test",
        subcategory="error",
        title="Exploding heuristic",
    )
    def check_explode(self, appspec: AppSpec) -> list[Finding]:
        raise RuntimeError("boom")


# =============================================================================
# Tests
# =============================================================================


class TestHeuristicDecorator:
    def test_attaches_metadata(self) -> None:
        agent = _StubAgent()
        meta = agent.check_first._heuristic_meta
        assert isinstance(meta, HeuristicMeta)
        assert meta.heuristic_id == "STUB-01"
        assert meta.category == "test"

    def test_non_heuristic_method_has_no_meta(self) -> None:
        agent = _StubAgent()
        assert not hasattr(agent.not_a_heuristic, "_heuristic_meta")


class TestGetHeuristics:
    def test_discovers_decorated_methods(self) -> None:
        agent = _StubAgent()
        heuristics = agent.get_heuristics()
        assert len(heuristics) == 2

    def test_sorted_by_id(self) -> None:
        agent = _StubAgent()
        heuristics = agent.get_heuristics()
        ids = [meta.heuristic_id for meta, _ in heuristics]
        assert ids == ["STUB-01", "STUB-02"]


class TestAgentRun:
    def test_returns_agent_result(self, simple_appspec: object) -> None:
        agent = _StubAgent()
        result = agent.run(simple_appspec)  # type: ignore[arg-type]
        assert isinstance(result, AgentResult)
        assert result.agent == AgentId.DI
        assert result.heuristics_run == 2
        assert len(result.findings) == 1

    def test_captures_errors(self, simple_appspec: object) -> None:
        agent = _ErrorAgent()
        result = agent.run(simple_appspec)  # type: ignore[arg-type]
        assert result.heuristics_run == 1
        assert len(result.errors) == 1
        assert "boom" in result.errors[0]
        assert result.findings == []

    def test_measures_duration(self, simple_appspec: object) -> None:
        agent = _StubAgent()
        result = agent.run(simple_appspec)  # type: ignore[arg-type]
        assert result.duration_ms >= 0
