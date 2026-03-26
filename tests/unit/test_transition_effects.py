"""Tests for transition side-effect runner (#435)."""

from unittest.mock import AsyncMock

import pytest

from dazzle.core.ir.process import EffectAction, FieldAssignment, StepEffect
from dazzle_back.runtime.side_effect_executor import EffectContext, EffectResult
from dazzle_back.runtime.transition_effects import (
    MAX_CASCADE_DEPTH,
    TransitionEffectRunner,
    _cascade_depth,
)


def _make_effect(action: str = "create", entity: str = "Task") -> StepEffect:
    return StepEffect(
        action=EffectAction(action),
        entity_name=entity,
        assignments=[FieldAssignment(field_path="title", value='"test"')],
    )


def _make_runner(
    entity_transitions: dict | None = None,
    status_fields: dict | None = None,
    executor: AsyncMock | None = None,
) -> tuple[TransitionEffectRunner, AsyncMock]:
    if executor is None:
        executor = AsyncMock()
        executor.execute_effects = AsyncMock(
            return_value=[EffectResult(action="create", entity_name="Task")]
        )
    if entity_transitions is None:
        entity_transitions = {
            "Order": [("draft", "submitted", [_make_effect()])],
        }
    if status_fields is None:
        status_fields = {"Order": "status"}
    runner = TransitionEffectRunner(
        executor=executor,
        entity_transitions=entity_transitions,
        status_fields=status_fields,
    )
    return runner, executor


@pytest.mark.asyncio
async def test_fires_on_matching_transition():
    runner, executor = _make_runner()
    await runner.on_entity_updated("Order", "id-1", {"status": "submitted"}, {"status": "draft"})
    executor.execute_effects.assert_called_once()
    args = executor.execute_effects.call_args
    assert len(args[0][0]) == 1
    assert isinstance(args[0][1], EffectContext)


@pytest.mark.asyncio
async def test_wildcard_matches_any_source():
    runner, executor = _make_runner(
        entity_transitions={
            "Order": [("*", "cancelled", [_make_effect()])],
        },
    )
    await runner.on_entity_updated("Order", "id-1", {"status": "cancelled"}, {"status": "active"})
    executor.execute_effects.assert_called_once()


@pytest.mark.asyncio
async def test_no_fire_when_status_unchanged():
    runner, executor = _make_runner()
    await runner.on_entity_updated("Order", "id-1", {"status": "draft"}, {"status": "draft"})
    executor.execute_effects.assert_not_called()


@pytest.mark.asyncio
async def test_no_fire_for_unknown_entity():
    runner, executor = _make_runner()
    await runner.on_entity_updated("Invoice", "id-1", {"status": "paid"}, {"status": "pending"})
    executor.execute_effects.assert_not_called()


@pytest.mark.asyncio
async def test_no_fire_when_no_old_data():
    runner, executor = _make_runner()
    await runner.on_entity_updated("Order", "id-1", {"status": "submitted"}, None)
    executor.execute_effects.assert_not_called()


@pytest.mark.asyncio
async def test_cascade_depth_limit():
    runner, executor = _make_runner()
    token = _cascade_depth.set(MAX_CASCADE_DEPTH)
    try:
        await runner.on_entity_updated(
            "Order", "id-1", {"status": "submitted"}, {"status": "draft"}
        )
        executor.execute_effects.assert_not_called()
    finally:
        _cascade_depth.reset(token)


@pytest.mark.asyncio
async def test_multiple_effects_all_fire():
    effects = [_make_effect(entity="Task"), _make_effect(entity="Log")]
    runner, executor = _make_runner(
        entity_transitions={"Order": [("draft", "submitted", effects)]},
    )
    executor.execute_effects = AsyncMock(
        return_value=[
            EffectResult(action="create", entity_name="Task"),
            EffectResult(action="create", entity_name="Log"),
        ]
    )
    await runner.on_entity_updated("Order", "id-1", {"status": "submitted"}, {"status": "draft"})
    executor.execute_effects.assert_called_once()
    called_effects = executor.execute_effects.call_args[0][0]
    assert len(called_effects) == 2


@pytest.mark.asyncio
async def test_failed_effect_logged_not_raised():
    runner, executor = _make_runner()
    executor.execute_effects = AsyncMock(
        return_value=[
            EffectResult(action="create", entity_name="Task", success=False, error="DB error")
        ]
    )
    # Should not raise
    await runner.on_entity_updated("Order", "id-1", {"status": "submitted"}, {"status": "draft"})
    executor.execute_effects.assert_called_once()
