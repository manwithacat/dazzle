"""
Base class and decorator for Sentinel detection agents.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dazzle.sentinel.models import AgentId, AgentResult, Finding

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec


@dataclass(frozen=True)
class HeuristicMeta:
    heuristic_id: str
    category: str
    subcategory: str
    title: str


def heuristic(
    heuristic_id: str,
    *,
    category: str,
    subcategory: str,
    title: str,
) -> Callable[..., Any]:
    """Mark a method as a detection heuristic with metadata."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func._heuristic_meta = HeuristicMeta(  # type: ignore[attr-defined]
            heuristic_id=heuristic_id,
            category=category,
            subcategory=subcategory,
            title=title,
        )
        return func

    return decorator


class DetectionAgent(ABC):
    """Abstract base for all Sentinel detection agents."""

    @property
    @abstractmethod
    def agent_id(self) -> AgentId: ...

    def get_heuristics(self) -> list[tuple[HeuristicMeta, Callable[..., list[Finding]]]]:
        """Discover @heuristic-decorated methods, sorted by heuristic ID."""
        results: list[tuple[HeuristicMeta, Callable[..., list[Finding]]]] = []
        for name in sorted(dir(self)):
            method = getattr(self, name, None)
            if callable(method) and hasattr(method, "_heuristic_meta"):
                meta: HeuristicMeta = method._heuristic_meta
                results.append((meta, method))
        results.sort(key=lambda x: x[0].heuristic_id)
        return results

    def run(self, appspec: AppSpec) -> AgentResult:
        """Run all heuristics against the given AppSpec."""
        t0 = time.monotonic()
        all_findings: list[Finding] = []
        errors: list[str] = []
        heuristics = self.get_heuristics()

        for meta, method in heuristics:
            try:
                findings = method(appspec)
                all_findings.extend(findings)
            except Exception as exc:
                errors.append(f"{meta.heuristic_id}: {exc}")

        elapsed = (time.monotonic() - t0) * 1000
        return AgentResult(
            agent=self.agent_id,
            findings=all_findings,
            heuristics_run=len(heuristics),
            duration_ms=round(elapsed, 2),
            errors=errors,
        )
