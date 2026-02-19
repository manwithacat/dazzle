"""
Unit tests for process side-effect actions (Issue #323).

Tests covering:
1. IR types — StepEffect, EffectAction creation and serialization
2. Parser — effects: block parsing with create/update, set, where
3. SideEffectExecutor — create effect, update effect, expression resolution
4. Validator — lint process effects
5. End-to-end: process with step effects triggers entity creation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.process import (
    EffectAction,
    FieldAssignment,
    ProcessSpec,
    ProcessStepSpec,
    StepEffect,
    StepKind,
)

# =========================================================================
# 1. IR Types
# =========================================================================


class TestEffectIRTypes:
    """Tests for EffectAction and StepEffect IR types."""

    def test_effect_action_values(self):
        assert EffectAction.CREATE == "create"
        assert EffectAction.UPDATE == "update"

    def test_step_effect_create(self):
        effect = StepEffect(
            action=EffectAction.CREATE,
            entity_name="Task",
            assignments=[
                FieldAssignment(field_path="title", value='"Confirm close"'),
                FieldAssignment(field_path="task_type", value='"period_close"'),
            ],
        )
        assert effect.action == EffectAction.CREATE
        assert effect.entity_name == "Task"
        assert effect.where is None
        assert len(effect.assignments) == 2

    def test_step_effect_update_with_where(self):
        effect = StepEffect(
            action=EffectAction.UPDATE,
            entity_name="ComplianceDeadline",
            where="linked_return_id = self.id",
            assignments=[
                FieldAssignment(field_path="status", value='"completed"'),
                FieldAssignment(field_path="completed_at", value="now()"),
            ],
        )
        assert effect.action == EffectAction.UPDATE
        assert effect.where == "linked_return_id = self.id"
        assert len(effect.assignments) == 2

    def test_step_effect_frozen(self):
        from pydantic import ValidationError

        effect = StepEffect(
            action=EffectAction.CREATE,
            entity_name="Task",
        )
        with pytest.raises(ValidationError):
            effect.entity_name = "Other"  # type: ignore[misc]

    def test_step_effect_serialization(self):
        effect = StepEffect(
            action=EffectAction.CREATE,
            entity_name="Task",
            assignments=[FieldAssignment(field_path="title", value='"Test"')],
        )
        data = effect.model_dump()
        assert data["action"] == "create"
        assert data["entity_name"] == "Task"
        assert len(data["assignments"]) == 1

    def test_process_step_with_effects(self):
        step = ProcessStepSpec(
            name="close_period",
            kind=StepKind.SERVICE,
            service="finalize_period",
            effects=[
                StepEffect(
                    action=EffectAction.CREATE,
                    entity_name="Task",
                    assignments=[
                        FieldAssignment(field_path="title", value='"Confirm"'),
                    ],
                ),
                StepEffect(
                    action=EffectAction.UPDATE,
                    entity_name="Deadline",
                    where="period_id = self.id",
                    assignments=[
                        FieldAssignment(field_path="status", value='"done"'),
                    ],
                ),
            ],
        )
        assert len(step.effects) == 2
        assert step.effects[0].action == EffectAction.CREATE
        assert step.effects[1].action == EffectAction.UPDATE

    def test_process_step_default_empty_effects(self):
        step = ProcessStepSpec(name="simple", kind=StepKind.SERVICE, service="svc")
        assert step.effects == []


# =========================================================================
# 2. Parser
# =========================================================================


class TestEffectsParser:
    """Tests for parsing effects: blocks in process steps."""

    def test_parse_step_with_create_effect(self):
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  task_type: str(50)

process bookkeeping_close "Bookkeeping Close":
  trigger: entity Task created
  steps:
    - step finalize:
        service: finalize_period
        effects:
          - create Task:
              set:
                - title -> "Confirm period close"
                - task_type -> "period_close_confirmation"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.processes) == 1
        process = fragment.processes[0]
        step = process.steps[0]
        assert len(step.effects) == 1

        effect = step.effects[0]
        assert effect.action == EffectAction.CREATE
        assert effect.entity_name == "Task"
        assert effect.where is None
        assert len(effect.assignments) == 2
        assert effect.assignments[0].field_path == "title"
        assert effect.assignments[0].value == "Confirm period close"
        assert effect.assignments[1].field_path == "task_type"
        assert effect.assignments[1].value == "period_close_confirmation"

    def test_parse_step_with_update_effect_and_where(self):
        dsl = """
module test.core
app MyApp "My App"

entity Deadline "Deadline":
  id: uuid pk
  status: str(50)
  linked_id: str(50)
  completed_at: datetime

process close_deadlines "Close Deadlines":
  trigger: entity Deadline created
  steps:
    - step close:
        service: close_service
        effects:
          - update Deadline:
              where: linked_id = self.id
              set:
                - status -> "completed"
                - completed_at -> now()
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        process = fragment.processes[0]
        step = process.steps[0]
        assert len(step.effects) == 1

        effect = step.effects[0]
        assert effect.action == EffectAction.UPDATE
        assert effect.entity_name == "Deadline"
        assert effect.where is not None
        assert "linked_id" in effect.where
        assert len(effect.assignments) == 2

    def test_parse_step_with_multiple_effects(self):
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

entity AuditLog "Audit Log":
  id: uuid pk
  message: str(500)

process multi_effect "Multi Effect":
  trigger: entity Task created
  steps:
    - step do_work:
        service: worker_service
        effects:
          - create Task:
              set:
                - title -> "Follow-up task"
          - create AuditLog:
              set:
                - message -> "Work completed"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        process = fragment.processes[0]
        step = process.steps[0]
        assert len(step.effects) == 2
        assert step.effects[0].entity_name == "Task"
        assert step.effects[1].entity_name == "AuditLog"

    def test_parse_step_without_effects(self):
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process simple "Simple":
  trigger: entity Order created
  steps:
    - step check:
        service: check_service
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        process = fragment.processes[0]
        step = process.steps[0]
        assert step.effects == []

    def test_parse_effects_with_self_reference(self):
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  ref_id: str(50)

entity Task "Task":
  id: uuid pk
  order_ref: str(50)

process order_task "Order Task":
  trigger: entity Order created
  steps:
    - step create_task:
        service: task_service
        effects:
          - create Task:
              set:
                - order_ref -> self.id
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        process = fragment.processes[0]
        step = process.steps[0]
        assert len(step.effects) == 1
        assert step.effects[0].assignments[0].value == "self.id"


# =========================================================================
# 3. SideEffectExecutor
# =========================================================================


class TestSideEffectExecutor:
    """Tests for SideEffectExecutor."""

    @pytest.fixture
    def mock_service(self):
        service = MagicMock()
        service.entity_name = "Task"

        # Create schema that accepts kwargs
        create_schema = MagicMock()
        create_schema.return_value = MagicMock()
        service.create_schema = create_schema

        # Update schema that accepts kwargs
        update_schema = MagicMock()
        update_schema.return_value = MagicMock()
        service.update_schema = update_schema

        # Mock create to return entity with id
        created_entity = MagicMock()
        created_entity.id = uuid4()
        service.create = AsyncMock(return_value=created_entity)

        # Mock update to return updated entity
        service.update = AsyncMock(return_value=MagicMock())

        # Mock list for where clause resolution
        service.list = AsyncMock(
            return_value={
                "items": [
                    {"id": str(uuid4()), "status": "pending"},
                    {"id": str(uuid4()), "status": "pending"},
                ],
                "total": 2,
            }
        )

        return service

    @pytest.fixture
    def executor(self, mock_service):
        from dazzle_back.runtime.side_effect_executor import SideEffectExecutor

        return SideEffectExecutor(services={"Task": mock_service})

    @pytest.fixture
    def effect_context(self):
        from dazzle_back.runtime.side_effect_executor import EffectContext

        return EffectContext(
            trigger_entity={"id": "trigger-123", "name": "Test Order"},
            process_inputs={"current_user": "admin"},
        )

    @pytest.mark.asyncio
    async def test_execute_create_effect(self, executor, mock_service, effect_context):
        effect = StepEffect(
            action=EffectAction.CREATE,
            entity_name="Task",
            assignments=[
                FieldAssignment(field_path="title", value='"Follow-up task"'),
                FieldAssignment(field_path="task_type", value='"review"'),
            ],
        )
        results = await executor.execute_effects([effect], effect_context)
        assert len(results) == 1
        assert results[0].success
        assert results[0].action == "create"
        assert results[0].entity_name == "Task"
        assert results[0].affected_count == 1

        # Verify create was called with resolved data
        mock_service.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_update_effect(self, executor, mock_service, effect_context):
        effect = StepEffect(
            action=EffectAction.UPDATE,
            entity_name="Task",
            where="order_id = trigger-123",
            assignments=[
                FieldAssignment(field_path="status", value='"completed"'),
            ],
        )
        results = await executor.execute_effects([effect], effect_context)
        assert len(results) == 1
        assert results[0].success
        assert results[0].action == "update"
        assert results[0].affected_count == 2  # 2 items from mock list

    @pytest.mark.asyncio
    async def test_execute_effect_missing_service(self, effect_context):
        from dazzle_back.runtime.side_effect_executor import SideEffectExecutor

        executor = SideEffectExecutor(services={})
        effect = StepEffect(
            action=EffectAction.CREATE,
            entity_name="NonExistent",
            assignments=[],
        )
        results = await executor.execute_effects([effect], effect_context)
        assert len(results) == 1
        assert not results[0].success
        assert "No service found" in (results[0].error or "")

    @pytest.mark.asyncio
    async def test_execute_multiple_effects(self, executor, mock_service, effect_context):
        effects = [
            StepEffect(
                action=EffectAction.CREATE,
                entity_name="Task",
                assignments=[
                    FieldAssignment(field_path="title", value='"Task 1"'),
                ],
            ),
            StepEffect(
                action=EffectAction.CREATE,
                entity_name="Task",
                assignments=[
                    FieldAssignment(field_path="title", value='"Task 2"'),
                ],
            ),
        ]
        results = await executor.execute_effects(effects, effect_context)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert mock_service.create.call_count == 2

    def test_resolve_string_literal(self, executor, effect_context):
        assert executor._resolve_value('"hello"', effect_context) == "hello"
        assert executor._resolve_value("'world'", effect_context) == "world"

    def test_resolve_self_reference(self, executor, effect_context):
        assert executor._resolve_value("self.id", effect_context) == "trigger-123"
        assert executor._resolve_value("self.name", effect_context) == "Test Order"

    def test_resolve_now(self, executor, effect_context):
        from datetime import datetime

        result = executor._resolve_value("now()", effect_context)
        assert isinstance(result, datetime)

    def test_resolve_current_user(self, executor, effect_context):
        result = executor._resolve_value("current_user()", effect_context)
        assert result == "admin"

    def test_resolve_boolean(self, executor, effect_context):
        assert executor._resolve_value("true", effect_context) is True
        assert executor._resolve_value("false", effect_context) is False

    def test_resolve_numeric(self, executor, effect_context):
        assert executor._resolve_value("42", effect_context) == 42
        assert executor._resolve_value("3.14", effect_context) == 3.14

    def test_resolve_bare_string(self, executor, effect_context):
        assert executor._resolve_value("completed", effect_context) == "completed"

    def test_resolve_assignments_strips_entity_prefix(self, executor, effect_context):
        assignments = [
            FieldAssignment(field_path="Task.title", value='"Test"'),
            FieldAssignment(field_path="status", value='"done"'),
        ]
        data = executor._resolve_assignments(assignments, effect_context)
        assert data == {"title": "Test", "status": "done"}

    @pytest.mark.asyncio
    async def test_update_without_where_returns_zero(self, executor, mock_service, effect_context):
        effect = StepEffect(
            action=EffectAction.UPDATE,
            entity_name="Task",
            # No where clause
            assignments=[
                FieldAssignment(field_path="status", value='"done"'),
            ],
        )
        results = await executor.execute_effects([effect], effect_context)
        assert len(results) == 1
        assert results[0].affected_count == 0


# =========================================================================
# 4. Validator
# =========================================================================


class TestProcessEffectsValidation:
    """Tests for process effects lint validation."""

    def _make_appspec_with_effects(self, effects, entity_fields=None):
        """Helper to create a minimal AppSpec with process effects."""
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec, EntitySpec
        from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind

        fields = entity_fields or [
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                is_primary_key=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
            ),
            FieldSpec(
                name="status",
                type=FieldType(kind=FieldTypeKind.STR, max_length=50),
            ),
        ]

        entity = EntitySpec(name="Task", title="Task", fields=fields)
        process = ProcessSpec(
            name="test_process",
            steps=[
                ProcessStepSpec(
                    name="test_step",
                    kind=StepKind.SERVICE,
                    service="test_svc",
                    effects=effects,
                )
            ],
        )
        domain = DomainSpec(entities=[entity])
        return AppSpec(
            name="test",
            title="Test",
            domain=domain,
            processes=[process],
        )

    def test_valid_effects_no_warnings(self):
        from dazzle.core.validator import _lint_process_effects

        appspec = self._make_appspec_with_effects(
            [
                StepEffect(
                    action=EffectAction.CREATE,
                    entity_name="Task",
                    assignments=[
                        FieldAssignment(field_path="title", value='"Test"'),
                    ],
                )
            ]
        )
        warnings = _lint_process_effects(appspec)
        assert len(warnings) == 0

    def test_invalid_entity_reference(self):
        from dazzle.core.validator import _lint_process_effects

        appspec = self._make_appspec_with_effects(
            [
                StepEffect(
                    action=EffectAction.CREATE,
                    entity_name="NonExistent",
                    assignments=[],
                )
            ]
        )
        warnings = _lint_process_effects(appspec)
        assert any("non-existent entity" in w for w in warnings)

    def test_invalid_field_reference(self):
        from dazzle.core.validator import _lint_process_effects

        appspec = self._make_appspec_with_effects(
            [
                StepEffect(
                    action=EffectAction.CREATE,
                    entity_name="Task",
                    assignments=[
                        FieldAssignment(field_path="nonexistent_field", value='"x"'),
                    ],
                )
            ]
        )
        warnings = _lint_process_effects(appspec)
        assert any("non-existent field" in w for w in warnings)

    def test_update_without_where_warning(self):
        from dazzle.core.validator import _lint_process_effects

        appspec = self._make_appspec_with_effects(
            [
                StepEffect(
                    action=EffectAction.UPDATE,
                    entity_name="Task",
                    assignments=[
                        FieldAssignment(field_path="status", value='"done"'),
                    ],
                )
            ]
        )
        warnings = _lint_process_effects(appspec)
        assert any("without" in w and "where" in w for w in warnings)

    def test_dotted_field_path_validated(self):
        from dazzle.core.validator import _lint_process_effects

        appspec = self._make_appspec_with_effects(
            [
                StepEffect(
                    action=EffectAction.CREATE,
                    entity_name="Task",
                    assignments=[
                        FieldAssignment(field_path="Task.title", value='"ok"'),
                    ],
                )
            ]
        )
        # Task.title -> field_name="title" which exists
        warnings = _lint_process_effects(appspec)
        assert len(warnings) == 0


# =========================================================================
# 5. Lexer token
# =========================================================================


class TestEffectsLexerToken:
    """Test that 'effects' is recognized as a keyword token."""

    def test_effects_is_keyword(self):
        from dazzle.core.lexer import KEYWORDS

        assert "effects" in KEYWORDS

    def test_effects_token_type(self):
        from dazzle.core.lexer import TokenType

        assert TokenType.EFFECTS.value == "effects"
