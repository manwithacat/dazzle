"""Tests for LLM intent trigger matcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.ir.llm import LLMTriggerEvent, LLMTriggerSpec
from dazzle_back.runtime.event_bus import EntityEvent, EntityEventType
from dazzle_back.runtime.llm_trigger import LLMTriggerMatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_appspec(intents=None):
    appspec = MagicMock()
    appspec.llm_intents = intents or []
    appspec.processes = []
    return appspec


def _make_intent(name, triggers):
    intent = MagicMock()
    intent.name = name
    intent.triggers = triggers
    return intent


def _make_event(entity_name, event_type, entity_id="123", data=None, user_id=None):
    return EntityEvent(
        event_type=event_type,
        entity_name=entity_name,
        entity_id=entity_id,
        data=data or {},
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Index Building
# ---------------------------------------------------------------------------


class TestTriggerIndex:
    def test_builds_index_from_intents(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.CREATED,
            input_map={"title": "entity.title"},
        )
        intent = _make_intent("classify", [trigger])
        matcher = LLMTriggerMatcher(_make_appspec([intent]), MagicMock())

        assert ("Ticket", LLMTriggerEvent.CREATED) in matcher._index
        assert len(matcher._index[("Ticket", LLMTriggerEvent.CREATED)]) == 1

    def test_multiple_triggers_same_event(self):
        t1 = LLMTriggerSpec(on_entity="Ticket", on_event=LLMTriggerEvent.CREATED, input_map={})
        t2 = LLMTriggerSpec(on_entity="Ticket", on_event=LLMTriggerEvent.CREATED, input_map={})
        i1 = _make_intent("classify", [t1])
        i2 = _make_intent("prioritize", [t2])
        matcher = LLMTriggerMatcher(_make_appspec([i1, i2]), MagicMock())

        assert len(matcher._index[("Ticket", LLMTriggerEvent.CREATED)]) == 2

    def test_empty_intents(self):
        matcher = LLMTriggerMatcher(_make_appspec([]), MagicMock())
        assert matcher._index == {}


# ---------------------------------------------------------------------------
# Input Mapping
# ---------------------------------------------------------------------------


class TestInputMapping:
    def test_maps_entity_fields(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.CREATED,
            input_map={"title": "entity.title", "body": "entity.description"},
        )
        intent = _make_intent("classify", [trigger])
        matcher = LLMTriggerMatcher(_make_appspec([intent]), MagicMock())

        event = _make_event(
            "Ticket", EntityEventType.CREATED, data={"title": "Bug", "description": "Crash"}
        )
        result = matcher._map_inputs(trigger.input_map, event)

        assert result == {"title": "Bug", "body": "Crash"}

    def test_maps_entity_id(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.CREATED,
            input_map={"ticket_id": "entity.id"},
        )
        intent = _make_intent("classify", [trigger])
        matcher = LLMTriggerMatcher(_make_appspec([intent]), MagicMock())

        event = _make_event("Ticket", EntityEventType.CREATED, entity_id="abc-123")
        result = matcher._map_inputs(trigger.input_map, event)

        assert result == {"ticket_id": "abc-123"}

    def test_literal_values_passed_through(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.CREATED,
            input_map={"mode": "auto"},
        )
        intent = _make_intent("classify", [trigger])
        matcher = LLMTriggerMatcher(_make_appspec([intent]), MagicMock())

        event = _make_event("Ticket", EntityEventType.CREATED)
        result = matcher._map_inputs(trigger.input_map, event)

        assert result == {"mode": "auto"}


# ---------------------------------------------------------------------------
# Condition Evaluation
# ---------------------------------------------------------------------------


class TestConditionEvaluation:
    def test_equality_condition(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.UPDATED,
            input_map={},
            when="entity.status == open",
        )
        intent = _make_intent("classify", [trigger])
        matcher = LLMTriggerMatcher(_make_appspec([intent]), MagicMock())

        event = _make_event("Ticket", EntityEventType.UPDATED, data={"status": "open"})
        assert matcher._evaluate_condition("entity.status == open", event) is True

        event2 = _make_event("Ticket", EntityEventType.UPDATED, data={"status": "closed"})
        assert matcher._evaluate_condition("entity.status == open", event2) is False

    def test_null_condition(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.UPDATED,
            input_map={},
            when="entity.category == null",
        )
        intent = _make_intent("classify", [trigger])
        matcher = LLMTriggerMatcher(_make_appspec([intent]), MagicMock())

        event = _make_event("Ticket", EntityEventType.UPDATED, data={"category": None})
        assert matcher._evaluate_condition("entity.category == null", event) is True

    def test_inequality_condition(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.UPDATED,
            input_map={},
            when="entity.status != closed",
        )
        intent = _make_intent("classify", [trigger])
        matcher = LLMTriggerMatcher(_make_appspec([intent]), MagicMock())

        event = _make_event("Ticket", EntityEventType.UPDATED, data={"status": "open"})
        assert matcher._evaluate_condition("entity.status != closed", event) is True


# ---------------------------------------------------------------------------
# Event Handling (full flow)
# ---------------------------------------------------------------------------


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_matching_event_submits_to_queue(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.CREATED,
            input_map={"title": "entity.title"},
        )
        intent = _make_intent("classify", [trigger])
        queue = MagicMock()
        queue.submit = AsyncMock(return_value="job-123")

        matcher = LLMTriggerMatcher(_make_appspec([intent]), queue)

        event = _make_event("Ticket", EntityEventType.CREATED, data={"title": "Bug report"})
        await matcher.handle_event(event)

        queue.submit.assert_called_once()
        call_kwargs = queue.submit.call_args
        assert call_kwargs[0][0] == "classify"
        assert call_kwargs[0][1] == {"title": "Bug report"}

    @pytest.mark.asyncio
    async def test_non_matching_entity_ignored(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.CREATED,
            input_map={},
        )
        intent = _make_intent("classify", [trigger])
        queue = MagicMock()
        queue.submit = AsyncMock()

        matcher = LLMTriggerMatcher(_make_appspec([intent]), queue)

        event = _make_event("User", EntityEventType.CREATED)
        await matcher.handle_event(event)

        queue.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_condition_prevents_trigger(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.UPDATED,
            input_map={"title": "entity.title"},
            when="entity.category == null",
        )
        intent = _make_intent("classify", [trigger])
        queue = MagicMock()
        queue.submit = AsyncMock()

        matcher = LLMTriggerMatcher(_make_appspec([intent]), queue)

        # Category already set — should not trigger
        event = _make_event(
            "Ticket", EntityEventType.UPDATED, data={"category": "billing", "title": "X"}
        )
        await matcher.handle_event(event)

        queue.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_back_callback_provided(self):
        trigger = LLMTriggerSpec(
            on_entity="Ticket",
            on_event=LLMTriggerEvent.CREATED,
            input_map={"title": "entity.title"},
            write_back={"Ticket.category": "output"},
        )
        intent = _make_intent("classify", [trigger])
        queue = MagicMock()
        queue.submit = AsyncMock(return_value="job-123")

        matcher = LLMTriggerMatcher(_make_appspec([intent]), queue)

        event = _make_event("Ticket", EntityEventType.CREATED, data={"title": "Test"})
        await matcher.handle_event(event)

        # Should have a callback argument
        call_kwargs = queue.submit.call_args
        assert call_kwargs[1].get("callback") is not None
