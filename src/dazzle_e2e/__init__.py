"""
DAZZLE E2E Testing Harness.

This package provides Playwright-based E2E testing infrastructure
that operates on semantic identifiers from the AppSpec.

Usage:
    from dazzle_e2e import DazzleLocators, run_flow

    async def test_create_task(page):
        locators = DazzleLocators(page)
        await locators.action("Task.create").click()
        await locators.field("Task.title").fill("New Task")
        await locators.action("Task.save").click()
        assert await locators.entity("Task").count() > 0

Usability checking:
    from dazzle_e2e import UsabilityChecker, check_usability

    checker = UsabilityChecker(testspec.usability_rules)
    result = checker.check_testspec(testspec)
    if result.errors:
        print(f"Found {result.errors} usability errors")

Accessibility checking:
    from dazzle_e2e import AccessibilityChecker, run_accessibility_check

    result = await run_accessibility_check(page, testspec, level="AA")
    if not result.passed:
        for entity, violations in result.violations_by_entity.items():
            print(f"Entity {entity} has {len(violations)} a11y issues")
"""

from dazzle_e2e.accessibility import (
    A11yCheckResult,
    AccessibilityChecker,
    AxeResults,
    AxeViolation,
    run_accessibility_check,
)
from dazzle_e2e.assertions import DazzleAssertions
from dazzle_e2e.harness import FlowRunner, run_flow
from dazzle_e2e.locators import DazzleLocators
from dazzle_e2e.usability import UsabilityChecker, UsabilityViolation, check_usability
from dazzle_e2e.wcag_mapping import (
    WCAGMapper,
    WCAGMappingResult,
    WCAGViolationMapping,
    format_violation_report,
    map_violations_to_appspec,
)

__all__ = [
    # Locators and assertions
    "DazzleLocators",
    "DazzleAssertions",
    # Flow execution
    "FlowRunner",
    "run_flow",
    # Usability checking
    "UsabilityChecker",
    "UsabilityViolation",
    "check_usability",
    # Accessibility checking
    "AccessibilityChecker",
    "A11yCheckResult",
    "AxeResults",
    "AxeViolation",
    "run_accessibility_check",
    # WCAG mapping
    "WCAGMapper",
    "WCAGMappingResult",
    "WCAGViolationMapping",
    "map_violations_to_appspec",
    "format_violation_report",
]
