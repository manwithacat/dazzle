"""
Tests for LLM models (Pydantic data structures).
"""

from dazzle.llm.models import (
    BusinessRule,
    BusinessRuleType,
    CRUDAnalysis,
    CRUDOperation,
    ImpliedTransition,
    Question,
    QuestionCategory,
    QuestionPriority,
    SpecAnalysis,
    StateMachine,
    StateTransition,
)


class TestStateMachine:
    """Tests for StateMachine model."""

    def test_create_state_machine(self):
        """Test creating a state machine."""
        sm = StateMachine(
            entity="Ticket",
            field="status",
            states=["open", "in_progress", "closed"],
            transitions_found=[],
            transitions_implied_but_missing=[],
            states_without_exit=[],
            unreachable_states=[],
        )

        assert sm.entity == "Ticket"
        assert sm.field == "status"
        assert len(sm.states) == 3
        assert "open" in sm.states

    def test_state_transition_with_alias(self):
        """Test state transition with 'from'/'to' aliases."""
        transition = StateTransition(
            **{
                "from": "open",
                "to": "closed",
                "trigger": "close ticket",
                "who_can_trigger": "admin",
            }
        )

        assert transition.from_state == "open"
        assert transition.to_state == "closed"
        assert transition.trigger == "close ticket"

    def test_implied_transition(self):
        """Test implied transition model."""
        implied = ImpliedTransition(
            **{
                "from": "closed",
                "to": "open",
                "reason": "reopening tickets mentioned but not specified",
                "question": "Can closed tickets be reopened?",
            }
        )

        assert implied.from_state == "closed"
        assert implied.to_state == "open"
        assert "reopen" in implied.reason.lower()


class TestCRUDAnalysis:
    """Tests for CRUD analysis models."""

    def test_crud_operation(self):
        """Test CRUD operation model."""
        op = CRUDOperation(
            found=True,
            location="SPEC.md:42",
            who="any user",
            constraints=["must be owner"],
        )

        assert op.found is True
        assert op.location == "SPEC.md:42"
        assert len(op.constraints) == 1

    def test_crud_analysis(self):
        """Test CRUD analysis model."""
        crud = CRUDAnalysis(
            entity="Task",
            operations_mentioned={
                "create": {"found": True, "location": "SPEC.md:10"},
                "read": {"found": True, "location": "SPEC.md:15"},
                "update": {"found": True, "location": "SPEC.md:20"},
                "delete": {"found": False, "question": "Can users delete tasks?"},
            },
            missing_operations=["delete"],
        )

        assert crud.entity == "Task"
        assert len(crud.operations_mentioned) == 4
        assert "delete" in crud.missing_operations


class TestBusinessRule:
    """Tests for business rule models."""

    def test_validation_rule(self):
        """Test validation business rule."""
        rule = BusinessRule(
            type=BusinessRuleType.VALIDATION,
            entity="User",
            field="email",
            rule="must be unique and valid email format",
            location="SPEC.md:50",
        )

        assert rule.type == BusinessRuleType.VALIDATION
        assert rule.entity == "User"
        assert rule.field == "email"
        assert "unique" in rule.rule

    def test_access_control_rule(self):
        """Test access control rule."""
        rule = BusinessRule(
            type=BusinessRuleType.ACCESS_CONTROL,
            entity="Ticket",
            field="status",
            rule="only admins can close tickets",
        )

        assert rule.type == BusinessRuleType.ACCESS_CONTROL
        assert "admin" in rule.rule.lower()


class TestQuestions:
    """Tests for question models."""

    def test_question(self):
        """Test question model."""
        q = Question(
            q="Who can delete tickets?",
            context="Deletion mentioned but permissions not specified",
            options=["Anyone", "Admin only", "Owner or admin"],
            impacts="Access control logic, UI buttons",
        )

        assert len(q.options) == 3
        assert "admin" in q.options[1].lower()

    def test_question_category(self):
        """Test question category."""
        cat = QuestionCategory(
            category="Access Control",
            priority=QuestionPriority.HIGH,
            questions=[
                Question(
                    q="Who can create tickets?",
                    context="Not specified",
                    options=["Anyone", "Registered users only"],
                    impacts="Authentication requirements",
                )
            ],
        )

        assert cat.category == "Access Control"
        assert cat.priority == QuestionPriority.HIGH
        assert len(cat.questions) == 1


class TestSpecAnalysis:
    """Tests for SpecAnalysis model and helper methods."""

    def test_create_spec_analysis(self):
        """Test creating a spec analysis."""
        analysis = SpecAnalysis(
            state_machines=[
                StateMachine(
                    entity="Task",
                    field="status",
                    states=["todo", "done"],
                    transitions_found=[
                        StateTransition(
                            **{"from": "todo", "to": "done", "trigger": "complete task"}
                        )
                    ],
                )
            ],
            crud_analysis=[
                CRUDAnalysis(
                    entity="Task",
                    operations_mentioned={
                        "create": {"found": True},
                        "read": {"found": True},
                    },
                    missing_operations=["update", "delete"],
                )
            ],
        )

        assert len(analysis.state_machines) == 1
        assert len(analysis.crud_analysis) == 1

    def test_get_all_questions(self):
        """Test getting all questions."""
        analysis = SpecAnalysis(
            clarifying_questions=[
                QuestionCategory(
                    category="State Machines",
                    priority=QuestionPriority.HIGH,
                    questions=[
                        Question(
                            q="Q1?",
                            context="C1",
                            options=["A", "B"],
                            impacts="I1",
                        ),
                        Question(
                            q="Q2?",
                            context="C2",
                            options=["A", "B"],
                            impacts="I2",
                        ),
                    ],
                ),
                QuestionCategory(
                    category="CRUD",
                    priority=QuestionPriority.MEDIUM,
                    questions=[
                        Question(
                            q="Q3?",
                            context="C3",
                            options=["A", "B"],
                            impacts="I3",
                        )
                    ],
                ),
            ]
        )

        all_questions = analysis.get_all_questions()
        assert len(all_questions) == 3

    def test_get_high_priority_questions(self):
        """Test filtering high priority questions."""
        analysis = SpecAnalysis(
            clarifying_questions=[
                QuestionCategory(
                    category="State Machines",
                    priority=QuestionPriority.HIGH,
                    questions=[
                        Question(
                            q="Q1?",
                            context="C1",
                            options=["A", "B"],
                            impacts="I1",
                        )
                    ],
                ),
                QuestionCategory(
                    category="CRUD",
                    priority=QuestionPriority.MEDIUM,
                    questions=[
                        Question(
                            q="Q2?",
                            context="C2",
                            options=["A", "B"],
                            impacts="I2",
                        )
                    ],
                ),
            ]
        )

        high_priority = analysis.get_high_priority_questions()
        assert len(high_priority) == 1
        assert high_priority[0].q == "Q1?"

    def test_get_question_count(self):
        """Test question count."""
        analysis = SpecAnalysis(
            clarifying_questions=[
                QuestionCategory(
                    category="State Machines",
                    priority=QuestionPriority.HIGH,
                    questions=[
                        Question(q="Q1?", context="C", options=["A"], impacts="I"),
                        Question(q="Q2?", context="C", options=["A"], impacts="I"),
                    ],
                )
            ]
        )

        assert analysis.get_question_count() == 2

    def test_state_machine_coverage(self):
        """Test state machine coverage calculation."""
        analysis = SpecAnalysis(
            state_machines=[
                StateMachine(
                    entity="Task",
                    field="status",
                    states=["todo", "in_progress", "done"],
                    transitions_found=[
                        StateTransition(
                            **{"from": "todo", "to": "in_progress", "trigger": "start"}
                        ),
                        StateTransition(
                            **{"from": "in_progress", "to": "done", "trigger": "complete"}
                        ),
                    ],
                    transitions_implied_but_missing=[
                        ImpliedTransition(
                            **{
                                "from": "todo",
                                "to": "done",
                                "reason": "skip in progress",
                                "question": "Can tasks go directly to done?",
                            }
                        )
                    ],
                )
            ]
        )

        coverage = analysis.get_state_machine_coverage()
        assert coverage["total_state_machines"] == 1
        assert coverage["found_transitions"] == 2
        assert coverage["missing_transitions"] == 1
        assert coverage["total_transitions"] == 3
        # 2 found out of 3 total = 66.7%
        assert 65 < coverage["coverage_percent"] < 67

    def test_crud_coverage(self):
        """Test CRUD coverage calculation."""
        analysis = SpecAnalysis(
            crud_analysis=[
                CRUDAnalysis(
                    entity="Task",
                    operations_mentioned={
                        "create": {"found": True},
                        "read": {"found": True},
                        "update": {"found": True},
                    },
                    missing_operations=["delete", "list"],
                ),
                CRUDAnalysis(
                    entity="User",
                    operations_mentioned={
                        "create": {"found": True},
                        "read": {"found": True},
                    },
                    missing_operations=["update", "delete", "list"],
                ),
            ]
        )

        coverage = analysis.get_crud_coverage()
        assert coverage["total_entities"] == 2
        assert coverage["total_operations"] == 10  # 2 entities × 5 operations
        assert coverage["missing_operations"] == 5  # 2 + 3
        # 5 found out of 10 = 50%
        assert coverage["coverage_percent"] == 50.0

    def test_empty_analysis(self):
        """Test empty analysis returns reasonable defaults."""
        analysis = SpecAnalysis()

        assert len(analysis.state_machines) == 0
        assert len(analysis.crud_analysis) == 0
        assert analysis.get_question_count() == 0

        sm_coverage = analysis.get_state_machine_coverage()
        assert sm_coverage["coverage_percent"] == 100.0  # No SMs = 100% complete

        crud_coverage = analysis.get_crud_coverage()
        assert crud_coverage["coverage_percent"] == 100.0  # No entities = 100% complete
