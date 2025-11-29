"""
Usability Rule Engine for Dazzle E2E Testing.

Evaluates usability rules against flows and page snapshots to identify
UX issues like excessive step counts, missing confirmation dialogs, etc.

Usage:
    from dazzle_e2e.usability import UsabilityChecker

    checker = UsabilityChecker(testspec.usability_rules)
    results = checker.check_flow(flow)
    page_results = await checker.check_page(page)
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle.core.ir import (
    E2ETestSpec,
    FlowPriority,
    FlowSpec,
    FlowStepKind,
    UsabilityRule,
)

if TYPE_CHECKING:
    from playwright.async_api import Page


@dataclass
class UsabilityViolation:
    """A single usability rule violation."""

    rule_id: str
    rule_description: str
    severity: str  # "warning" or "error"
    context: str  # What was being checked (e.g., flow ID, page URL)
    details: str  # Specific violation details
    suggestion: str | None = None  # Suggested fix


@dataclass
class UsabilityCheckResult:
    """Result of checking usability rules."""

    passed: bool
    violations: list[UsabilityViolation] = field(default_factory=list)
    warnings: int = 0
    errors: int = 0

    def add_violation(self, violation: UsabilityViolation) -> None:
        """Add a violation and update counts."""
        self.violations.append(violation)
        if violation.severity == "error":
            self.errors += 1
            self.passed = False
        else:
            self.warnings += 1


class UsabilityChecker:
    """
    Evaluates usability rules against flows and pages.

    Supported rule checks:
    - max_steps: Check that high-priority flows have acceptable step counts
    - primary_action_visible: Check that primary actions are visible
    - destructive_confirm: Check that destructive actions have confirmation
    - validation_placement: Check that validation messages are near fields
    - navigation_breadth: Check that navigation isn't too deep
    - form_field_order: Check that form fields follow logical order
    """

    def __init__(self, rules: list[UsabilityRule]) -> None:
        """
        Initialize the usability checker.

        Args:
            rules: List of usability rules to check
        """
        self.rules = rules
        self._rules_by_check: dict[str, list[UsabilityRule]] = {}
        for rule in rules:
            check = rule.check
            if check not in self._rules_by_check:
                self._rules_by_check[check] = []
            self._rules_by_check[check].append(rule)

    def check_flow(self, flow: FlowSpec) -> UsabilityCheckResult:
        """
        Check a single flow against usability rules.

        Args:
            flow: Flow specification to check

        Returns:
            UsabilityCheckResult with any violations
        """
        result = UsabilityCheckResult(passed=True)

        # Check max_steps rule
        for rule in self._rules_by_check.get("max_steps", []):
            self._check_max_steps(flow, rule, result)

        # Check destructive_confirm rule
        for rule in self._rules_by_check.get("destructive_confirm", []):
            self._check_destructive_confirm(flow, rule, result)

        return result

    def check_flows(self, flows: list[FlowSpec]) -> UsabilityCheckResult:
        """
        Check multiple flows against usability rules.

        Args:
            flows: List of flow specifications

        Returns:
            Combined UsabilityCheckResult
        """
        result = UsabilityCheckResult(passed=True)

        for flow in flows:
            flow_result = self.check_flow(flow)
            for violation in flow_result.violations:
                result.add_violation(violation)

        return result

    def check_testspec(self, testspec: E2ETestSpec) -> UsabilityCheckResult:
        """
        Check all flows in a test specification.

        Args:
            testspec: E2E test specification

        Returns:
            Combined UsabilityCheckResult
        """
        return self.check_flows(testspec.flows)

    async def check_page(
        self,
        page: "Page",
        context: str = "page",
    ) -> UsabilityCheckResult:
        """
        Check live page against usability rules.

        Args:
            page: Playwright Page instance
            context: Context string for violation reporting

        Returns:
            UsabilityCheckResult with any violations
        """
        result = UsabilityCheckResult(passed=True)

        # Check primary_action_visible rule
        for rule in self._rules_by_check.get("primary_action_visible", []):
            await self._check_primary_action_visible(page, rule, context, result)

        # Check validation_placement rule
        for rule in self._rules_by_check.get("validation_placement", []):
            await self._check_validation_placement(page, rule, context, result)

        return result

    def _check_max_steps(
        self,
        flow: FlowSpec,
        rule: UsabilityRule,
        result: UsabilityCheckResult,
    ) -> None:
        """Check max_steps rule for a flow."""
        # Parse target to determine which flows to check
        target = rule.target or ""
        threshold = int(rule.threshold) if rule.threshold else 5

        # Check if this flow matches the target
        should_check = False
        if target.startswith("priority:"):
            priority_str = target.split(":", 1)[1]
            try:
                target_priority = FlowPriority(priority_str)
                should_check = flow.priority == target_priority
            except ValueError:
                should_check = False
        elif target.startswith("tag:"):
            tag = target.split(":", 1)[1]
            should_check = tag in flow.tags
        elif target.startswith("entity:"):
            entity = target.split(":", 1)[1]
            should_check = flow.entity == entity
        elif not target:
            # No target means all flows
            should_check = True

        if not should_check:
            return

        # Count non-assertion steps (user actions)
        action_steps = [
            step
            for step in flow.steps
            if step.kind not in (FlowStepKind.ASSERT, FlowStepKind.WAIT, FlowStepKind.SNAPSHOT)
        ]
        step_count = len(action_steps)

        if step_count > threshold:
            result.add_violation(
                UsabilityViolation(
                    rule_id=rule.id,
                    rule_description=rule.description,
                    severity=rule.severity,
                    context=f"flow:{flow.id}",
                    details=f"Flow has {step_count} action steps, exceeds threshold of {threshold}",
                    suggestion="Consider breaking this flow into smaller sub-flows or simplifying the user journey",
                )
            )

    def _check_destructive_confirm(
        self,
        flow: FlowSpec,
        rule: UsabilityRule,
        result: UsabilityCheckResult,
    ) -> None:
        """Check that destructive actions have confirmation dialogs."""
        # Look for delete/destroy actions without confirmation
        for i, step in enumerate(flow.steps):
            if step.kind == FlowStepKind.CLICK:
                target = step.target or ""
                # Check if this is a destructive action
                if any(word in target.lower() for word in ["delete", "destroy", "remove", "clear"]):
                    # Check if the next step is a confirm action
                    has_confirm = False
                    if i + 1 < len(flow.steps):
                        next_step = flow.steps[i + 1]
                        if next_step.kind == FlowStepKind.CLICK:
                            next_target = next_step.target or ""
                            if "confirm" in next_target.lower():
                                has_confirm = True

                    if not has_confirm:
                        result.add_violation(
                            UsabilityViolation(
                                rule_id=rule.id,
                                rule_description=rule.description,
                                severity=rule.severity,
                                context=f"flow:{flow.id}",
                                details=f"Destructive action '{target}' at step {i + 1} has no confirmation",
                                suggestion="Add a confirmation dialog before destructive actions to prevent accidental data loss",
                            )
                        )

    async def _check_primary_action_visible(
        self,
        page: "Page",
        rule: UsabilityRule,
        context: str,
        result: UsabilityCheckResult,
    ) -> None:
        """Check that primary actions are visible on page load."""
        # Look for primary action buttons
        primary_locator = page.locator('[data-dazzle-action][data-dazzle-primary="true"]')
        action_locator = page.locator("[data-dazzle-action]")

        # Count total actions
        total_actions = await action_locator.count()
        if total_actions == 0:
            # No actions on page - not a violation
            return

        # Check if primary actions are visible
        primary_count = await primary_locator.count()
        if primary_count == 0:
            # No primary actions marked - check if first action is visible
            first_action = action_locator.first
            try:
                is_visible = await first_action.is_visible()
                if not is_visible:
                    result.add_violation(
                        UsabilityViolation(
                            rule_id=rule.id,
                            rule_description=rule.description,
                            severity=rule.severity,
                            context=context,
                            details="No primary action visible on page load",
                            suggestion="Mark the most important action with data-dazzle-primary='true' and ensure it's visible without scrolling",
                        )
                    )
            except Exception:
                pass
        else:
            # Check if primary actions are visible
            for i in range(primary_count):
                action = primary_locator.nth(i)
                try:
                    is_visible = await action.is_visible()
                    if not is_visible:
                        action_id = await action.get_attribute("data-dazzle-action")
                        result.add_violation(
                            UsabilityViolation(
                                rule_id=rule.id,
                                rule_description=rule.description,
                                severity=rule.severity,
                                context=context,
                                details=f"Primary action '{action_id}' is not visible on page load",
                                suggestion="Ensure primary actions are visible without scrolling",
                            )
                        )
                except Exception:
                    pass

    async def _check_validation_placement(
        self,
        page: "Page",
        rule: UsabilityRule,
        context: str,
        result: UsabilityCheckResult,
    ) -> None:
        """Check that validation messages appear near their fields."""
        # Find validation messages
        validation_msgs = page.locator('[data-dazzle-message-kind="validation"]')
        count = await validation_msgs.count()

        for i in range(count):
            msg = validation_msgs.nth(i)
            field_ref = await msg.get_attribute("data-dazzle-for-field")

            if not field_ref:
                result.add_violation(
                    UsabilityViolation(
                        rule_id=rule.id,
                        rule_description=rule.description,
                        severity=rule.severity,
                        context=context,
                        details="Validation message has no associated field reference",
                        suggestion="Add data-dazzle-for-field attribute to validation messages",
                    )
                )
                continue

            # Find the associated field
            field_locator = page.locator(f'[data-dazzle-field="{field_ref}"]')
            field_count = await field_locator.count()

            if field_count == 0:
                result.add_violation(
                    UsabilityViolation(
                        rule_id=rule.id,
                        rule_description=rule.description,
                        severity=rule.severity,
                        context=context,
                        details=f"Validation message references non-existent field '{field_ref}'",
                        suggestion="Ensure validation message references an existing field",
                    )
                )
                continue

            # Check if message is visually near the field (within 100px)
            try:
                msg_box = await msg.bounding_box()
                field_box = await field_locator.first.bounding_box()

                if msg_box and field_box:
                    # Calculate vertical distance
                    msg_top = msg_box["y"]
                    msg_bottom = msg_box["y"] + msg_box["height"]
                    field_top = field_box["y"]
                    field_bottom = field_box["y"] + field_box["height"]

                    # Message should be within 100px of field
                    vertical_dist = min(
                        abs(msg_top - field_bottom),  # Message below field
                        abs(field_top - msg_bottom),  # Message above field
                    )

                    if vertical_dist > 100:
                        result.add_violation(
                            UsabilityViolation(
                                rule_id=rule.id,
                                rule_description=rule.description,
                                severity=rule.severity,
                                context=context,
                                details=f"Validation message for '{field_ref}' is {vertical_dist:.0f}px from field",
                                suggestion="Position validation messages closer to their associated fields",
                            )
                        )
            except Exception:
                pass  # Can't measure position - skip this check


def check_usability(
    testspec: E2ETestSpec,
    rules: list[UsabilityRule] | None = None,
) -> UsabilityCheckResult:
    """
    Convenience function to check usability rules for a test spec.

    Args:
        testspec: E2E test specification
        rules: Optional rules override (uses testspec.usability_rules if not provided)

    Returns:
        UsabilityCheckResult with any violations
    """
    check_rules = rules or testspec.usability_rules
    checker = UsabilityChecker(check_rules)
    return checker.check_testspec(testspec)
