"""/ux-cycle Strategy.FITNESS wiring.

Invoked by the top-level ux_cycle runner when it rotates to FITNESS. Owns
example-app lifecycle (starts runtime, runs the engine, tears down) and
aggregates the result into a /ux-cycle outcome.

v1 ships the strategy entry point only — the real ``_build_engine`` factory
is a v1.0.1 follow-up. It currently raises ``NotImplementedError`` so the
wiring is testable via dependency injection but will fail loudly if a caller
tries to run it without providing a mock engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class StrategyOutcome:
    """Aggregated outcome from one /ux-cycle strategy run."""

    strategy: str
    summary: str
    degraded: bool
    findings_count: int


async def run_fitness_strategy(example_app: str, project_root: Path) -> StrategyOutcome:
    """Run one fitness cycle against ``example_app`` and return a summary.

    Tests patch :func:`_build_engine` to inject a fake engine. Production
    callers need to wait for the v1.0.1 integration that wires real
    ``RuntimeServices`` dependencies.
    """
    engine = _build_engine(example_app=example_app, project_root=project_root)
    result = await engine.run()
    summary = (
        f"fitness run {result.run_metadata.get('run_id')}: "
        f"{len(result.findings)} findings, "
        f"independence={result.independence_jaccard:.3f}"
    )
    return StrategyOutcome(
        strategy="FITNESS",
        summary=summary,
        degraded=result.profile.degraded,
        findings_count=len(result.findings),
    )


def _build_engine(example_app: str, project_root: Path) -> Any:
    """Construct a FitnessEngine for the given example app.

    Factory function so tests can patch it cleanly. The real implementation
    needs Task 0 discovery notes to wire up the snapshot source, DazzleAgent,
    PlaywrightExecutor, and the LLM facade from the example's RuntimeServices.
    """
    raise NotImplementedError(
        "fitness_strategy._build_engine: wire RuntimeServices + DazzleAgent "
        "after Task 0 discovery of engine dependencies"
    )
