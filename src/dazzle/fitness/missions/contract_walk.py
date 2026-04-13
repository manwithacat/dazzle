"""Contract-driven Pass 1 walker (v1.0.2 task 1).

Mirrors the shape of ``walker.walk_story`` but drives the ledger from a
parsed ux-architect ``ComponentContract`` instead of a DSL story. Each
quality gate becomes one ledger step: its description is recorded as the
EXPECT, the walker calls an injected observer's ``snapshot()`` method to
capture the current UI state as OBSERVE, and a fixed action description
marks the step as a contract observation rather than a user action.

The walker is deterministic — no LLM calls. The observer is injected so
unit tests can pass an in-memory stub and the fitness strategy can wrap
a Playwright ``page`` with a thin adapter.
"""

from __future__ import annotations

from typing import Protocol

from dazzle.agent.missions._shared import ComponentContract
from dazzle.fitness.walker import WalkResult


class _ObserverLike(Protocol):
    async def snapshot(self) -> str: ...


class _LedgerLike(Protocol):
    def record_intent(self, step: int, expect: str, action_desc: str) -> None: ...
    def observe_step(self, step: int, observed_ui: str) -> None: ...


_ACTION_DESC = "observe contract gate"


async def walk_contract(
    contract: ComponentContract,
    observer: _ObserverLike,
    ledger: _LedgerLike,
) -> WalkResult:
    """Drive the ledger through one observation per quality gate.

    For each gate in ``contract.quality_gates``:

    1. Record the intent with ``expect = gate.description``
    2. Call ``await observer.snapshot()`` to capture the UI state
    3. Record the observation with ``observed_ui = <snapshot>``

    Exceptions raised by ``observer.snapshot()`` are captured into the
    result's ``errors`` list and a synthetic ``"error: <msg>"`` observation
    is recorded, so the walk always produces symmetric intent/observation
    counts per step.
    """
    result = WalkResult(
        story_id=f"contract:{contract.component_name}",
        persona="fitness_contract",
        steps_executed=0,
    )

    for idx, gate in enumerate(contract.quality_gates, start=1):
        ledger.record_intent(step=idx, expect=gate.description, action_desc=_ACTION_DESC)
        result.steps_executed += 1

        try:
            observed = await observer.snapshot()
        except Exception as e:  # noqa: BLE001 — surfacing the error into the ledger is the point
            observed = f"error: {e}"
            result.errors.append(f"step {idx}: {e}")

        ledger.observe_step(step=idx, observed_ui=observed)

    return result
