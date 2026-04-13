"""Tests for walk_contract — deterministic contract-driven Pass 1 walker."""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.agent.missions._shared import ComponentContract, QualityGate
from dazzle.fitness.missions.contract_walk import walk_contract


class _FakeObserver:
    def __init__(self, snapshots: list[str]) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    async def snapshot(self) -> str:
        self.calls += 1
        if self._snapshots:
            return self._snapshots.pop(0)
        return "empty"


class _FakeLedger:
    def __init__(self) -> None:
        self.intents: list[dict[str, Any]] = []
        self.observations: list[dict[str, Any]] = []

    def record_intent(self, step: int, expect: str, action_desc: str) -> None:
        self.intents.append({"step": step, "expect": expect, "action_desc": action_desc})

    def observe_step(self, step: int, observed_ui: str) -> None:
        self.observations.append({"step": step, "observed_ui": observed_ui})


@pytest.mark.asyncio
async def test_walk_contract_records_one_step_per_gate() -> None:
    contract = ComponentContract(
        component_name="auth-page",
        quality_gates=[
            QualityGate(id="card_layout", description="Card is centered in viewport"),
            QualityGate(id="submit_primary", description="Submit button uses primary color"),
            QualityGate(id="error_hidden", description="Error div starts hidden"),
        ],
    )
    observer = _FakeObserver(
        snapshots=["<html>card</html>", "<html>submit</html>", "<html>error</html>"]
    )
    ledger = _FakeLedger()

    result = await walk_contract(contract=contract, observer=observer, ledger=ledger)

    assert result.story_id == "contract:auth-page"
    assert result.persona == "fitness_contract"
    assert result.steps_executed == 3
    assert result.errors == []

    # Each gate produced one intent + one observation
    assert len(ledger.intents) == 3
    assert len(ledger.observations) == 3

    # Step numbers are 1-indexed
    assert [i["step"] for i in ledger.intents] == [1, 2, 3]
    assert [o["step"] for o in ledger.observations] == [1, 2, 3]

    # Intent's expect == gate description (verbatim)
    assert ledger.intents[0]["expect"] == "Card is centered in viewport"
    assert ledger.intents[1]["expect"] == "Submit button uses primary color"
    assert ledger.intents[2]["expect"] == "Error div starts hidden"

    # Action description is a fixed contract-walker string
    assert all(i["action_desc"] == "observe contract gate" for i in ledger.intents)

    # Observation text is the observer's snapshot output
    assert ledger.observations[0]["observed_ui"] == "<html>card</html>"
    assert ledger.observations[1]["observed_ui"] == "<html>submit</html>"
    assert ledger.observations[2]["observed_ui"] == "<html>error</html>"

    # The observer was called exactly once per gate
    assert observer.calls == 3


@pytest.mark.asyncio
async def test_walk_contract_empty_gates_returns_zero_steps() -> None:
    contract = ComponentContract(component_name="empty", quality_gates=[])
    observer = _FakeObserver(snapshots=[])
    ledger = _FakeLedger()

    result = await walk_contract(contract=contract, observer=observer, ledger=ledger)

    assert result.story_id == "contract:empty"
    assert result.steps_executed == 0
    assert result.errors == []
    assert ledger.intents == []
    assert ledger.observations == []
    assert observer.calls == 0


@pytest.mark.asyncio
async def test_walk_contract_captures_observer_error_per_step() -> None:
    """If observer.snapshot() raises, the walker records the error and continues."""
    contract = ComponentContract(
        component_name="flaky",
        quality_gates=[
            QualityGate(id="first", description="First gate"),
            QualityGate(id="second", description="Second gate"),
        ],
    )

    class _RaisingObserver:
        def __init__(self) -> None:
            self.calls = 0

        async def snapshot(self) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("snapshot boom")
            return "ok"

    observer = _RaisingObserver()
    ledger = _FakeLedger()

    result = await walk_contract(contract=contract, observer=observer, ledger=ledger)

    assert result.steps_executed == 2
    assert len(result.errors) == 1
    assert "snapshot boom" in result.errors[0]

    # First observation recorded the error string, second recorded "ok"
    assert "error: snapshot boom" in ledger.observations[0]["observed_ui"]
    assert ledger.observations[1]["observed_ui"] == "ok"
