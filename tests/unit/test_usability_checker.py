"""Unit tests for usability rule engine."""

from dazzle.core.ir import (
    E2ETestSpec,
    FlowAssertion,
    FlowAssertionKind,
    FlowPriority,
    FlowSpec,
    FlowStep,
    FlowStepKind,
    UsabilityRule,
)
from dazzle_e2e.usability import UsabilityChecker, check_usability

# =============================================================================
# Test Data Factories
# =============================================================================


def make_flow(
    flow_id: str = "test_flow",
    priority: FlowPriority = FlowPriority.MEDIUM,
    steps: list[FlowStep] | None = None,
    tags: list[str] | None = None,
    entity: str | None = None,
) -> FlowSpec:
    """Create a test flow."""
    return FlowSpec(
        id=flow_id,
        description=f"Test flow: {flow_id}",
        priority=priority,
        steps=steps or [],
        tags=tags or [],
        entity=entity,
    )


def make_step(
    kind: FlowStepKind,
    target: str | None = None,
    description: str = "Test step",
) -> FlowStep:
    """Create a test step."""
    return FlowStep(
        kind=kind,
        target=target,
        description=description,
    )


def make_assert_step(
    kind: FlowAssertionKind = FlowAssertionKind.VISIBLE,
    target: str = "test",
) -> FlowStep:
    """Create a test assert step."""
    return FlowStep(
        kind=FlowStepKind.ASSERT,
        assertion=FlowAssertion(kind=kind, target=target),
        description="Test assertion",
    )


# =============================================================================
# Max Steps Rule Tests
# =============================================================================


class TestMaxStepsRule:
    """Tests for max_steps usability rule."""

    def test_high_priority_under_threshold(self):
        """High priority flow under threshold should pass."""
        rule = UsabilityRule(
            id="max_steps_high",
            description="High priority flows should complete in 5 steps or less",
            check="max_steps",
            threshold=5,
            target="priority:high",
            severity="warning",
        )

        flow = make_flow(
            flow_id="short_flow",
            priority=FlowPriority.HIGH,
            steps=[
                make_step(FlowStepKind.NAVIGATE, "view:list"),
                make_step(FlowStepKind.CLICK, "action:create"),
                make_step(FlowStepKind.FILL, "field:title"),
                make_step(FlowStepKind.CLICK, "action:save"),
            ],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.passed
        assert result.errors == 0
        assert result.warnings == 0

    def test_high_priority_over_threshold(self):
        """High priority flow over threshold should fail."""
        rule = UsabilityRule(
            id="max_steps_high",
            description="High priority flows should complete in 5 steps or less",
            check="max_steps",
            threshold=5,
            target="priority:high",
            severity="warning",
        )

        flow = make_flow(
            flow_id="long_flow",
            priority=FlowPriority.HIGH,
            steps=[
                make_step(FlowStepKind.NAVIGATE, "view:list"),
                make_step(FlowStepKind.CLICK, "action:create"),
                make_step(FlowStepKind.FILL, "field:title"),
                make_step(FlowStepKind.FILL, "field:desc"),
                make_step(FlowStepKind.FILL, "field:status"),
                make_step(FlowStepKind.FILL, "field:priority"),
                make_step(FlowStepKind.CLICK, "action:save"),
            ],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.passed  # Warnings don't fail
        assert result.warnings == 1
        assert result.errors == 0
        assert "7 action steps" in result.violations[0].details

    def test_assertions_not_counted(self):
        """Assert and wait steps should not count toward step limit."""
        rule = UsabilityRule(
            id="max_steps_high",
            description="High priority flows should complete in 5 steps or less",
            check="max_steps",
            threshold=5,
            target="priority:high",
            severity="warning",
        )

        flow = make_flow(
            flow_id="flow_with_assertions",
            priority=FlowPriority.HIGH,
            steps=[
                make_step(FlowStepKind.NAVIGATE, "view:list"),
                make_step(FlowStepKind.CLICK, "action:create"),
                make_step(FlowStepKind.WAIT),
                make_step(FlowStepKind.FILL, "field:title"),
                make_assert_step(),
                make_step(FlowStepKind.CLICK, "action:save"),
                make_assert_step(),
                make_step(FlowStepKind.SNAPSHOT),
            ],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        # Only 4 action steps: navigate, click, fill, click
        assert result.passed
        assert result.warnings == 0

    def test_medium_priority_not_checked(self):
        """Medium priority flow should not be checked when target is high."""
        rule = UsabilityRule(
            id="max_steps_high",
            description="High priority flows should complete in 5 steps or less",
            check="max_steps",
            threshold=5,
            target="priority:high",
            severity="warning",
        )

        flow = make_flow(
            flow_id="long_medium_flow",
            priority=FlowPriority.MEDIUM,
            steps=[make_step(FlowStepKind.CLICK, f"action:{i}") for i in range(10)],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.passed
        assert result.warnings == 0

    def test_check_all_flows_no_target(self):
        """Rule with no target should check all flows."""
        rule = UsabilityRule(
            id="max_steps_all",
            description="All flows should be under 10 steps",
            check="max_steps",
            threshold=10,
            severity="warning",
        )

        flow = make_flow(
            flow_id="long_flow",
            priority=FlowPriority.LOW,
            steps=[make_step(FlowStepKind.CLICK, f"action:{i}") for i in range(12)],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.warnings == 1

    def test_target_by_tag(self):
        """Rule can target flows by tag."""
        rule = UsabilityRule(
            id="max_steps_crud",
            description="CRUD flows should be under 6 steps",
            check="max_steps",
            threshold=6,
            target="tag:crud",
            severity="error",
        )

        crud_flow = make_flow(
            flow_id="crud_flow",
            tags=["crud", "create"],
            steps=[make_step(FlowStepKind.CLICK, f"action:{i}") for i in range(8)],
        )

        non_crud_flow = make_flow(
            flow_id="other_flow",
            tags=["navigation"],
            steps=[make_step(FlowStepKind.CLICK, f"action:{i}") for i in range(8)],
        )

        checker = UsabilityChecker([rule])

        crud_result = checker.check_flow(crud_flow)
        assert not crud_result.passed
        assert crud_result.errors == 1

        other_result = checker.check_flow(non_crud_flow)
        assert other_result.passed

    def test_target_by_entity(self):
        """Rule can target flows by entity."""
        rule = UsabilityRule(
            id="max_steps_task",
            description="Task flows should be quick",
            check="max_steps",
            threshold=4,
            target="entity:Task",
            severity="warning",
        )

        task_flow = make_flow(
            flow_id="task_flow",
            entity="Task",
            steps=[make_step(FlowStepKind.CLICK, f"action:{i}") for i in range(6)],
        )

        user_flow = make_flow(
            flow_id="user_flow",
            entity="User",
            steps=[make_step(FlowStepKind.CLICK, f"action:{i}") for i in range(6)],
        )

        checker = UsabilityChecker([rule])

        task_result = checker.check_flow(task_flow)
        assert task_result.warnings == 1

        user_result = checker.check_flow(user_flow)
        assert user_result.warnings == 0

    def test_error_severity(self):
        """Error severity should cause check to fail."""
        rule = UsabilityRule(
            id="max_steps_critical",
            description="Critical limit",
            check="max_steps",
            threshold=3,
            severity="error",
        )

        flow = make_flow(
            steps=[make_step(FlowStepKind.CLICK, f"action:{i}") for i in range(5)],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert not result.passed
        assert result.errors == 1


# =============================================================================
# Destructive Confirm Rule Tests
# =============================================================================


class TestDestructiveConfirmRule:
    """Tests for destructive_confirm usability rule."""

    def test_delete_with_confirm(self):
        """Delete action with confirmation should pass."""
        rule = UsabilityRule(
            id="destructive_confirm",
            description="Destructive actions should have confirmation",
            check="destructive_confirm",
            severity="error",
        )

        flow = make_flow(
            steps=[
                make_step(FlowStepKind.NAVIGATE, "view:list"),
                make_step(FlowStepKind.CLICK, "action:Task.delete"),
                make_step(FlowStepKind.CLICK, "action:confirm"),
            ],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.passed
        assert result.errors == 0

    def test_delete_without_confirm(self):
        """Delete action without confirmation should fail."""
        rule = UsabilityRule(
            id="destructive_confirm",
            description="Destructive actions should have confirmation",
            check="destructive_confirm",
            severity="error",
        )

        flow = make_flow(
            steps=[
                make_step(FlowStepKind.NAVIGATE, "view:list"),
                make_step(FlowStepKind.CLICK, "action:Task.delete"),
                make_assert_step(),
            ],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert not result.passed
        assert result.errors == 1
        assert "no confirmation" in result.violations[0].details.lower()

    def test_remove_action_checked(self):
        """Remove action should also be checked."""
        rule = UsabilityRule(
            id="destructive_confirm",
            description="Destructive actions should have confirmation",
            check="destructive_confirm",
            severity="warning",
        )

        flow = make_flow(
            steps=[
                make_step(FlowStepKind.CLICK, "action:Item.remove"),
                make_step(FlowStepKind.NAVIGATE, "view:list"),
            ],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.warnings == 1

    def test_non_destructive_not_checked(self):
        """Non-destructive actions should not require confirmation."""
        rule = UsabilityRule(
            id="destructive_confirm",
            description="Destructive actions should have confirmation",
            check="destructive_confirm",
            severity="error",
        )

        flow = make_flow(
            steps=[
                make_step(FlowStepKind.CLICK, "action:Task.create"),
                make_step(FlowStepKind.CLICK, "action:Task.save"),
                make_step(FlowStepKind.CLICK, "action:Task.edit"),
            ],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.passed


# =============================================================================
# Integration Tests
# =============================================================================


class TestUsabilityIntegration:
    """Integration tests for usability checking."""

    def test_check_flows(self):
        """Check multiple flows at once."""
        rule = UsabilityRule(
            id="max_steps",
            description="Flows under 5 steps",
            check="max_steps",
            threshold=5,
            severity="warning",
        )

        flows = [
            make_flow(
                flow_id="short",
                steps=[make_step(FlowStepKind.CLICK, "a")],
            ),
            make_flow(
                flow_id="long",
                steps=[make_step(FlowStepKind.CLICK, f"a{i}") for i in range(7)],
            ),
        ]

        checker = UsabilityChecker([rule])
        result = checker.check_flows(flows)

        assert result.passed
        assert result.warnings == 1
        assert "flow:long" in result.violations[0].context

    def test_check_testspec(self):
        """Check complete E2E test spec."""
        rules = [
            UsabilityRule(
                id="max_steps",
                description="Flows under 5 steps",
                check="max_steps",
                threshold=5,
                severity="warning",
            ),
            UsabilityRule(
                id="destructive_confirm",
                description="Destructive confirm",
                check="destructive_confirm",
                severity="error",
            ),
        ]

        flows = [
            make_flow(
                flow_id="create",
                steps=[make_step(FlowStepKind.CLICK, f"a{i}") for i in range(7)],
            ),
            make_flow(
                flow_id="delete_bad",
                steps=[
                    make_step(FlowStepKind.CLICK, "action:delete"),
                ],
            ),
        ]

        testspec = E2ETestSpec(
            app_name="test",
            version="1.0",
            flows=flows,
            usability_rules=rules,
        )

        result = check_usability(testspec)

        assert not result.passed
        assert result.warnings == 1  # max_steps
        assert result.errors == 1  # destructive confirm
        assert len(result.violations) == 2

    def test_multiple_rules_same_check(self):
        """Multiple rules for same check should all be evaluated."""
        rules = [
            UsabilityRule(
                id="max_steps_high",
                description="High priority under 3",
                check="max_steps",
                threshold=3,
                target="priority:high",
                severity="error",
            ),
            UsabilityRule(
                id="max_steps_all",
                description="All under 10",
                check="max_steps",
                threshold=10,
                severity="warning",
            ),
        ]

        flow = make_flow(
            flow_id="test",
            priority=FlowPriority.HIGH,
            steps=[make_step(FlowStepKind.CLICK, f"a{i}") for i in range(5)],
        )

        checker = UsabilityChecker(rules)
        result = checker.check_flow(flow)

        # Fails high priority rule, passes all rule
        assert not result.passed
        assert result.errors == 1
        assert result.warnings == 0


class TestViolationDetails:
    """Tests for violation detail fields."""

    def test_violation_has_suggestion(self):
        """Violations should include suggestions."""
        rule = UsabilityRule(
            id="max_steps",
            description="Test",
            check="max_steps",
            threshold=2,
            severity="warning",
        )

        flow = make_flow(
            steps=[make_step(FlowStepKind.CLICK, f"a{i}") for i in range(5)],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert result.violations[0].suggestion is not None
        assert len(result.violations[0].suggestion) > 0

    def test_violation_context(self):
        """Violations should have context."""
        rule = UsabilityRule(
            id="max_steps",
            description="Test",
            check="max_steps",
            threshold=2,
            severity="warning",
        )

        flow = make_flow(
            flow_id="my_flow_id",
            steps=[make_step(FlowStepKind.CLICK, f"a{i}") for i in range(5)],
        )

        checker = UsabilityChecker([rule])
        result = checker.check_flow(flow)

        assert "my_flow_id" in result.violations[0].context
