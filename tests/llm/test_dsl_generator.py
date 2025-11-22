"""
Tests for DSL generator.
"""

import pytest
from dazzle.llm.dsl_generator import DSLGenerator
from dazzle.llm.models import (
    SpecAnalysis,
    StateMachine,
    StateTransition,
    ImpliedTransition,
    CRUDAnalysis,
    CRUDOperation,
    BusinessRule,
    BusinessRuleType,
)


@pytest.fixture
def simple_task_analysis():
    """Fixture for simple task manager analysis."""
    return SpecAnalysis(
        state_machines=[
            StateMachine(
                entity="Task",
                field="status",
                states=["todo", "in_progress", "done"],
                transitions_found=[
                    StateTransition(
                        **{
                            "from": "todo",
                            "to": "in_progress",
                            "trigger": "start working",
                            "who_can_trigger": "anyone",
                        }
                    ),
                    StateTransition(
                        **{
                            "from": "in_progress",
                            "to": "done",
                            "trigger": "mark complete",
                            "who_can_trigger": "anyone",
                        }
                    ),
                ],
                transitions_implied_but_missing=[
                    ImpliedTransition(
                        **{
                            "from": "todo",
                            "to": "done",
                            "reason": "quick completion mentioned",
                            "question": "Can tasks skip in_progress?",
                        }
                    )
                ],
            )
        ],
        crud_analysis=[
            CRUDAnalysis(
                entity="Task",
                operations_mentioned={
                    "create": CRUDOperation(found=True, location="SPEC.md:20"),
                    "read": CRUDOperation(found=True, location="SPEC.md:25"),
                    "update": CRUDOperation(found=True, location="SPEC.md:30"),
                    "delete": CRUDOperation(found=True, location="SPEC.md:35"),
                    "list": CRUDOperation(found=True, location="SPEC.md:15"),
                },
                missing_operations=[],
            )
        ],
        business_rules=[
            BusinessRule(
                type=BusinessRuleType.VALIDATION,
                entity="Task",
                field="title",
                rule="required, max 200 characters",
            ),
            BusinessRule(
                type=BusinessRuleType.VALIDATION,
                entity="Task",
                field="description",
                rule="optional, text field",
            ),
        ],
    )


@pytest.fixture
def ticket_analysis():
    """Fixture for support ticket analysis."""
    return SpecAnalysis(
        state_machines=[
            StateMachine(
                entity="Ticket",
                field="status",
                states=["open", "in_progress", "resolved", "closed"],
                transitions_found=[
                    StateTransition(
                        **{
                            "from": "open",
                            "to": "in_progress",
                            "trigger": "assign to support",
                            "who_can_trigger": "support staff",
                        }
                    ),
                    StateTransition(
                        **{
                            "from": "in_progress",
                            "to": "resolved",
                            "trigger": "mark resolved",
                            "who_can_trigger": "support staff",
                        }
                    ),
                ],
            )
        ],
        crud_analysis=[
            CRUDAnalysis(
                entity="Ticket",
                operations_mentioned={
                    "create": CRUDOperation(found=True, who="any user"),
                    "read": CRUDOperation(found=True, who="ticket creator or support"),
                    "update": CRUDOperation(found=True, who="support staff"),
                    "delete": CRUDOperation(found=False, question="Can tickets be deleted?"),
                    "list": CRUDOperation(found=True, filters_needed=["status", "priority"]),
                },
                missing_operations=["delete"],
            ),
            CRUDAnalysis(
                entity="User",
                operations_mentioned={
                    "create": CRUDOperation(found=True),
                    "read": CRUDOperation(found=True),
                },
                missing_operations=["update", "delete", "list"],
            ),
        ],
    )


class TestDSLGenerator:
    """Tests for DSL generator."""

    def test_generate_header(self, simple_task_analysis):
        """Test generating DSL header."""
        generator = DSLGenerator(simple_task_analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        assert "module task_manager" in dsl
        assert 'app task_manager "Task Manager"' in dsl
        assert "# Generated by DAZZLE" in dsl

    def test_generate_entity_with_state_machine(self, simple_task_analysis):
        """Test generating entity with state machine field."""
        generator = DSLGenerator(simple_task_analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        # Should have Task entity
        assert "entity Task" in dsl

        # Should have status field with enum
        assert "status: enum[todo,in_progress,done]" in dsl

        # Should have standard fields
        assert "id: uuid pk" in dsl
        assert "created_at: datetime auto_add" in dsl
        assert "updated_at: datetime auto_update" in dsl

    def test_generate_surfaces_for_crud(self, simple_task_analysis):
        """Test generating surfaces for CRUD operations."""
        generator = DSLGenerator(simple_task_analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        # Should have all CRUD surfaces
        assert "surface task_list" in dsl
        assert "surface task_detail" in dsl
        assert "surface task_create" in dsl
        assert "surface task_edit" in dsl

        # Check modes
        assert "mode: list" in dsl
        assert "mode: view" in dsl
        assert "mode: create" in dsl
        assert "mode: edit" in dsl

    def test_generate_state_machine_docs(self, simple_task_analysis):
        """Test generating state machine documentation."""
        generator = DSLGenerator(simple_task_analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        # Should have state machine section
        assert "STATE MACHINES" in dsl
        assert "State Machine: Task.status" in dsl
        assert "States: todo, in_progress, done" in dsl

        # Should document transitions
        assert "todo → in_progress" in dsl
        assert "Trigger: start working" in dsl

        # Should document missing transitions
        assert "⚠ todo → done" in dsl
        assert "quick completion" in dsl

    def test_generate_business_rules_docs(self, simple_task_analysis):
        """Test generating business rules documentation."""
        generator = DSLGenerator(simple_task_analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        # Should have business rules section
        assert "BUSINESS RULES" in dsl
        assert "VALIDATION:" in dsl

        # Should document rules
        assert "Task.title" in dsl
        assert "required, max 200" in dsl

    def test_infer_common_fields(self, simple_task_analysis):
        """Test inferring common fields for task entities."""
        generator = DSLGenerator(simple_task_analysis)
        fields = generator._infer_entity_fields("Task")

        # Should have common task fields
        assert "title" in fields
        assert "description" in fields
        assert "id" in fields
        assert "created_at" in fields

    def test_generate_with_answers(self, simple_task_analysis):
        """Test generating DSL with user answers."""
        answers = {
            "Can tasks skip in_progress?": "Yes",
            "Who can delete tasks?": "Admin only",
        }

        generator = DSLGenerator(simple_task_analysis, answers)
        dsl = generator.generate("task_manager", "Task Manager")

        # Should still generate valid DSL
        assert "entity Task" in dsl
        assert "surface task_list" in dsl

    def test_multiple_entities(self, ticket_analysis):
        """Test generating DSL with multiple entities."""
        generator = DSLGenerator(ticket_analysis)
        dsl = generator.generate("support", "Support System")

        # Should have both entities
        assert "entity Ticket" in dsl
        assert "entity User" in dsl

        # Should have surfaces for Ticket (which has full CRUD)
        assert "surface ticket_list" in dsl
        assert "surface ticket_detail" in dsl
        assert "surface ticket_create" in dsl
        # Note: ticket_edit might be there if update is found

        # User should have minimal surfaces (only create/read found)
        # (Current implementation generates surfaces based on operations_mentioned)

    def test_surface_field_selection(self, simple_task_analysis):
        """Test surface field selection logic."""
        generator = DSLGenerator(simple_task_analysis)

        # List fields should be concise
        list_fields = generator._get_list_fields("Task")
        assert ("title", "Title") in list_fields
        assert ("created_at", "Created") in list_fields

        # Detail fields should be comprehensive
        detail_fields = generator._get_detail_fields("Task")
        assert ("title", "Title") in detail_fields
        assert ("description", "Description") in detail_fields
        assert ("created_at", "Created") in detail_fields
        assert ("updated_at", "Last Updated") in detail_fields

        # Create fields should exclude auto fields
        create_fields = generator._get_create_fields("Task")
        assert ("title", "Title") in create_fields
        assert ("description", "Description") in create_fields
        # Should NOT have created_at (auto field)
        field_names = [name for name, _ in create_fields]
        assert "created_at" not in field_names

    def test_empty_analysis(self):
        """Test generating from empty analysis."""
        analysis = SpecAnalysis()
        generator = DSLGenerator(analysis)
        dsl = generator.generate("app", "My App")

        # Should still generate valid DSL structure
        assert "module app" in dsl
        assert 'app app "My App"' in dsl
        assert "ENTITIES" in dsl

    def test_generate_validates_as_dsl(self, simple_task_analysis):
        """Test that generated DSL is syntactically valid."""
        generator = DSLGenerator(simple_task_analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        # Basic syntax checks
        lines = dsl.split("\n")

        # Should not have syntax errors
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                # Entity/surface/app declarations should have colons
                if stripped.startswith(("entity", "surface", "section")):
                    assert ":" in line, f"Missing colon in: {line}"

                # Field declarations should have colons
                if not stripped.startswith(
                    ("entity", "surface", "section", "mode:", "uses")
                ):
                    # This is likely a field
                    if not line.strip().startswith("#"):
                        # Should be properly indented
                        assert line.startswith((" ", "\t")) or line.startswith(
                            ("module", "app", "#")
                        ), f"Bad indentation: {line}"
