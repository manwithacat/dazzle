"""Tests for the Pass 1 deterministic story walker (v1 fitness task 12).

The walker is async because it drives an external async executor
(Playwright), but the fitness ledger itself is sync (see Task 4). The
``_LedgerLike`` stub therefore uses a plain ``MagicMock`` for
``observe_step`` rather than ``AsyncMock``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.fitness.walker import WalkResult, walk_story


class _Story:
    def __init__(self, id: str, persona: str, steps: list[dict]) -> None:
        self.id = id
        self.persona = persona
        self.steps = steps


@pytest.mark.asyncio
async def test_walker_runs_all_steps_and_records_intents() -> None:
    executor = MagicMock()
    executor.goto = AsyncMock()
    executor.click = AsyncMock()
    executor.fill = AsyncMock()

    ledger = MagicMock()
    ledger.observe_step = MagicMock()
    ledger.record_intent = MagicMock()

    story = _Story(
        id="s1",
        persona="support_agent",
        steps=[
            {"action": "goto", "url": "/tickets", "expect": "queue page"},
            {"action": "click", "selector": "#new", "expect": "form opens"},
        ],
    )

    result: WalkResult = await walk_story(story=story, executor=executor, ledger=ledger)

    assert result.steps_executed == 2
    assert result.errors == []
    assert ledger.record_intent.call_count == 2
    assert ledger.observe_step.call_count == 2
    executor.goto.assert_awaited_once_with("/tickets")
    executor.click.assert_awaited_once_with("#new")


@pytest.mark.asyncio
async def test_walker_records_error_on_executor_failure() -> None:
    executor = MagicMock()
    executor.goto = AsyncMock(side_effect=RuntimeError("navigation failed"))

    ledger = MagicMock()
    ledger.observe_step = MagicMock()
    ledger.record_intent = MagicMock()

    story = _Story(
        id="s1",
        persona="agent",
        steps=[{"action": "goto", "url": "/x", "expect": "page loads"}],
    )

    result = await walk_story(story=story, executor=executor, ledger=ledger)
    assert result.steps_executed == 1
    assert len(result.errors) == 1
    assert "navigation failed" in result.errors[0]
