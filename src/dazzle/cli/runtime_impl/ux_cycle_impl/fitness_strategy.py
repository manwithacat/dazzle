"""/ux-cycle Strategy.FITNESS wiring.

Invoked by the top-level ux_cycle runner when it rotates to FITNESS. Owns
example-app lifecycle (starts runtime, runs the engine, tears down) and
aggregates the result into a /ux-cycle outcome.

v1.0.1 wires the real dependencies across three tasks: ``_launch_example_app``
spins up the example via ``dazzle.qa.server`` (Task 3), ``_build_engine``
loads the example's ``AppSpec`` + ``FitnessConfig`` and constructs a
Playwright-backed ``FitnessEngine`` (Task 4), and ``_stop_example_app`` tears
down the subprocess (Task 3). Until both land, the helpers raise
``NotImplementedError`` and the unit tests patch them.
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

    Owns the example-app subprocess lifecycle via try/finally, so teardown
    runs even if the engine raises.
    """
    example_root = _resolve_example_root(example_app=example_app, project_root=project_root)
    handle = _launch_example_app(example_root=example_root)
    try:
        engine = _build_engine(example_root=example_root, handle=handle)
        result = await engine.run()
    finally:
        _stop_example_app(handle)

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


def _resolve_example_root(example_app: str, project_root: Path) -> Path:
    """Resolve ``examples/<example_app>`` relative to the Dazzle repo root."""
    return project_root / "examples" / example_app


def _launch_example_app(example_root: Path) -> Any:
    """Launch the example app subprocess and wait for its API to become ready.

    Returns an ``AppConnection``-compatible handle. Real implementation lands
    in Task 3.
    """
    raise NotImplementedError("fitness_strategy._launch_example_app: implemented in Task 3")


def _stop_example_app(handle: Any) -> None:
    """Terminate the example-app subprocess owned by ``handle``.

    Real implementation lands in Task 3.
    """
    raise NotImplementedError("fitness_strategy._stop_example_app: implemented in Task 3")


def _build_engine(example_root: Path, handle: Any) -> Any:
    """Construct a ``FitnessEngine`` for the given example app.

    Real implementation lands in Task 4.
    """
    raise NotImplementedError("fitness_strategy._build_engine: implemented in Task 4")
