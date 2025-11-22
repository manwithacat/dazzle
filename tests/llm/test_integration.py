"""
Integration tests for LLM workflow.
"""

import pytest
from dazzle.llm.models import SpecAnalysis
from dazzle.llm.dsl_generator import DSLGenerator
from .test_fixtures import MOCK_TASK_ANALYSIS_JSON, MOCK_TICKET_ANALYSIS_JSON


class TestEndToEndWorkflow:
    """Test complete workflow from analysis to DSL."""

    def test_task_manager_workflow(self):
        """Test complete workflow for simple task manager."""
        # Parse mock analysis
        analysis = SpecAnalysis(**MOCK_TASK_ANALYSIS_JSON)

        # Verify analysis parsed correctly
        assert len(analysis.state_machines) == 1
        assert analysis.state_machines[0].entity == "Task"
        assert len(analysis.crud_analysis) == 1
        assert len(analysis.business_rules) == 4

        # Check coverage metrics
        sm_coverage = analysis.get_state_machine_coverage()
        assert sm_coverage["total_state_machines"] == 1
        assert sm_coverage["found_transitions"] == 2
        assert sm_coverage["missing_transitions"] == 1

        crud_coverage = analysis.get_crud_coverage()
        assert crud_coverage["total_entities"] == 1
        assert crud_coverage["missing_operations"] == 0  # All CRUD operations found

        # Generate DSL
        generator = DSLGenerator(analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        # Verify DSL structure
        assert "module task_manager" in dsl
        assert "entity Task" in dsl
        assert "status: enum[todo,in_progress,done]" in dsl
        assert "surface task_list" in dsl
        assert "surface task_create" in dsl

    def test_support_tickets_workflow(self):
        """Test complete workflow for support tickets system."""
        # Parse mock analysis
        analysis = SpecAnalysis(**MOCK_TICKET_ANALYSIS_JSON)

        # Verify analysis
        assert len(analysis.state_machines) == 1
        assert len(analysis.crud_analysis) == 3  # Ticket, User, Comment
        assert len(analysis.clarifying_questions) == 3  # Categories

        # Check questions
        all_questions = analysis.get_all_questions()
        assert len(all_questions) == 4  # 2 + 1 + 1

        high_priority = analysis.get_high_priority_questions()
        assert len(high_priority) == 3  # 2 from State Machine + 1 from Access Control

        # Check coverage
        crud_coverage = analysis.get_crud_coverage()
        assert crud_coverage["total_entities"] == 3
        # Ticket: missing delete, User: missing 3, Comment: missing 3 = 7 total missing
        assert crud_coverage["missing_operations"] == 7

        # Generate DSL
        generator = DSLGenerator(analysis)
        dsl = generator.generate("support", "Support System")

        # Verify DSL has all entities
        assert "entity Ticket" in dsl
        assert "entity User" in dsl
        assert "entity Comment" in dsl

        # Verify state machine
        assert "status: enum[open,in_progress,resolved,closed]" in dsl

        # Verify state machine documentation
        assert "STATE MACHINES" in dsl
        assert "Ticket.status" in dsl
        assert "⚠" in dsl  # Missing transitions marker

    def test_workflow_with_answers(self):
        """Test workflow with user answers to questions."""
        analysis = SpecAnalysis(**MOCK_TASK_ANALYSIS_JSON)

        # Simulate user answering questions
        answers = {
            "Can users move tasks back from 'in progress' to 'to do'?": "Yes, users can move tasks back",
            "Should there be confirmation before deleting tasks?": "Yes, always confirm",
            "Can users filter tasks by date range?": "Yes, add date range filter",
        }

        # Generate DSL with answers
        generator = DSLGenerator(analysis, answers)
        dsl = generator.generate("task_manager", "Task Manager")

        # DSL should still be valid
        assert "module task_manager" in dsl
        assert "entity Task" in dsl

        # Note: Current generator doesn't use answers in DSL generation yet
        # In future, answers could influence field generation, surfaces, etc.

    def test_empty_spec_handling(self):
        """Test handling of empty/minimal spec."""
        # Create minimal analysis
        analysis = SpecAnalysis(
            state_machines=[],
            crud_analysis=[],
            business_rules=[],
            clarifying_questions=[],
        )

        # Should still generate valid DSL
        generator = DSLGenerator(analysis)
        dsl = generator.generate("minimal", "Minimal App")

        assert "module minimal" in dsl
        assert 'app minimal "Minimal App"' in dsl
        assert "ENTITIES" in dsl

        # Coverage should be 100% (nothing to cover)
        assert analysis.get_state_machine_coverage()["coverage_percent"] == 100.0
        assert analysis.get_crud_coverage()["coverage_percent"] == 100.0

    def test_analysis_to_dsl_preserves_intent(self):
        """Test that key spec information is preserved in DSL."""
        analysis = SpecAnalysis(**MOCK_TASK_ANALYSIS_JSON)

        generator = DSLGenerator(analysis)
        dsl = generator.generate("task_manager", "Task Manager")

        # Check that business rules are documented
        assert "title" in dsl.lower()
        assert "required" in dsl.lower() or "VALIDATION" in dsl

        # Check that state machine info is preserved
        assert "todo" in dsl
        assert "in_progress" in dsl
        assert "done" in dsl

        # Check that CRUD operations resulted in surfaces
        surfaces_mentioned = ["list", "detail", "create", "edit"]
        for surface_type in surfaces_mentioned:
            assert surface_type in dsl.lower()


class TestQuestionAnswering:
    """Test question handling and filtering."""

    def test_filter_by_priority(self):
        """Test filtering questions by priority."""
        analysis = SpecAnalysis(**MOCK_TICKET_ANALYSIS_JSON)

        # Get all questions
        all_q = analysis.get_all_questions()
        high_q = analysis.get_high_priority_questions()

        # High priority should be subset of all
        assert len(high_q) <= len(all_q)

        # All high priority questions should be high priority
        for q in high_q:
            found = False
            for cat in analysis.clarifying_questions:
                if cat.priority == "high" and q in cat.questions:
                    found = True
            assert found, f"Question {q.q} not in high priority category"

    def test_question_count(self):
        """Test question counting."""
        analysis = SpecAnalysis(**MOCK_TICKET_ANALYSIS_JSON)

        count = analysis.get_question_count()
        all_questions = analysis.get_all_questions()

        assert count == len(all_questions)
        assert count == 4  # Based on mock data


class TestCoverageMetrics:
    """Test coverage calculation."""

    def test_perfect_coverage(self):
        """Test analysis with perfect coverage."""
        analysis = SpecAnalysis(
            state_machines=[
                {
                    "entity": "Task",
                    "field": "status",
                    "states": ["todo", "done"],
                    "transitions_found": [
                        {"from": "todo", "to": "done", "trigger": "complete"}
                    ],
                    "transitions_implied_but_missing": [],
                }
            ],
            crud_analysis=[
                {
                    "entity": "Task",
                    "operations_mentioned": {
                        "create": {"found": True},
                        "read": {"found": True},
                        "update": {"found": True},
                        "delete": {"found": True},
                        "list": {"found": True},
                    },
                    "missing_operations": [],
                }
            ],
        )

        sm_coverage = analysis.get_state_machine_coverage()
        crud_coverage = analysis.get_crud_coverage()

        assert sm_coverage["coverage_percent"] == 100.0
        assert crud_coverage["coverage_percent"] == 100.0

    def test_partial_coverage(self):
        """Test analysis with gaps."""
        analysis = SpecAnalysis(
            state_machines=[
                {
                    "entity": "Task",
                    "field": "status",
                    "states": ["todo", "in_progress", "done"],
                    "transitions_found": [
                        {"from": "todo", "to": "in_progress", "trigger": "start"}
                    ],
                    "transitions_implied_but_missing": [
                        {
                            "from": "in_progress",
                            "to": "done",
                            "reason": "completion",
                            "question": "How to complete?",
                        },
                        {
                            "from": "todo",
                            "to": "done",
                            "reason": "skip",
                            "question": "Can skip?",
                        },
                    ],
                }
            ],
            crud_analysis=[
                {
                    "entity": "Task",
                    "operations_mentioned": {
                        "create": {"found": True},
                        "read": {"found": True},
                    },
                    "missing_operations": ["update", "delete", "list"],
                }
            ],
        )

        sm_coverage = analysis.get_state_machine_coverage()
        crud_coverage = analysis.get_crud_coverage()

        # 1 found out of 3 total transitions
        assert 30 < sm_coverage["coverage_percent"] < 35

        # 2 found out of 5 operations
        assert crud_coverage["coverage_percent"] == 40.0
