"""
Flow Execution Harness for Dazzle E2E Testing.

Executes FlowSpec definitions using Playwright, translating semantic
steps into browser actions.

Usage:
    from dazzle_e2e import FlowRunner

    async with FlowRunner(page, adapter) as runner:
        result = await runner.run_flow(flow)
        assert result.passed
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import (
    E2ETestSpec,
    FixtureSpec,
    FlowAssertion,
    FlowAssertionKind,
    FlowSpec,
    FlowStep,
    FlowStepKind,
)
from dazzle_e2e.assertions import DazzleAssertions
from dazzle_e2e.locators import DazzleLocators, get_locator_for_target

if TYPE_CHECKING:
    from playwright.async_api import Page

    from dazzle_e2e.adapters.base import BaseAdapter


@dataclass
class StepResult:
    """Result of executing a single flow step."""

    step: FlowStep
    passed: bool
    error: str | None = None
    duration_ms: float = 0


@dataclass
class FlowResult:
    """Result of executing a complete flow."""

    flow: FlowSpec
    passed: bool
    step_results: list[StepResult] = field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0
    fixtures_created: dict[str, Any] = field(default_factory=dict)

    @property
    def failed_step(self) -> StepResult | None:
        """Get the first failed step, if any."""
        for result in self.step_results:
            if not result.passed:
                return result
        return None


class FlowRunner:
    """
    Executes FlowSpec definitions using Playwright.

    Translates semantic flow steps into browser actions and assertions.
    """

    def __init__(
        self,
        page: "Page",
        adapter: "BaseAdapter",
        fixtures: dict[str, FixtureSpec] | None = None,
        default_timeout: int = 5000,
    ) -> None:
        """
        Initialize the flow runner.

        Args:
            page: Playwright Page instance
            adapter: Stack adapter for test operations
            fixtures: Optional pre-loaded fixtures dict
            default_timeout: Default timeout for operations (ms)
        """
        self.page = page
        self.adapter = adapter
        self.locators = DazzleLocators(page)
        self.assertions = DazzleAssertions(page, adapter)
        self.fixtures = fixtures or {}
        self.default_timeout = default_timeout
        self._fixture_data: dict[str, Any] = {}

    async def __aenter__(self) -> "FlowRunner":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - reset test data."""
        try:
            await self.adapter.reset()
        except Exception:
            pass  # Best effort cleanup

    async def run_flow(self, flow: FlowSpec) -> FlowResult:
        """
        Execute a complete flow.

        Args:
            flow: Flow specification to execute

        Returns:
            FlowResult with pass/fail status and step details
        """
        import time

        start_time = time.time()
        step_results: list[StepResult] = []

        try:
            # Apply preconditions
            if flow.preconditions:
                await self._apply_preconditions(flow)

            # Execute each step
            for step in flow.steps:
                step_start = time.time()
                try:
                    await self._execute_step(step)
                    step_results.append(
                        StepResult(
                            step=step,
                            passed=True,
                            duration_ms=(time.time() - step_start) * 1000,
                        )
                    )
                except Exception as e:
                    step_results.append(
                        StepResult(
                            step=step,
                            passed=False,
                            error=str(e),
                            duration_ms=(time.time() - step_start) * 1000,
                        )
                    )
                    # Stop on first failure
                    return FlowResult(
                        flow=flow,
                        passed=False,
                        step_results=step_results,
                        error=str(e),
                        duration_ms=(time.time() - start_time) * 1000,
                        fixtures_created=self._fixture_data,
                    )

            return FlowResult(
                flow=flow,
                passed=True,
                step_results=step_results,
                duration_ms=(time.time() - start_time) * 1000,
                fixtures_created=self._fixture_data,
            )

        except Exception as e:
            return FlowResult(
                flow=flow,
                passed=False,
                step_results=step_results,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
                fixtures_created=self._fixture_data,
            )

    async def _apply_preconditions(self, flow: FlowSpec) -> None:
        """Apply flow preconditions (fixtures, auth, etc.)."""
        if not flow.preconditions:
            return

        preconditions = flow.preconditions

        # Authenticate if required
        if preconditions.authenticated:
            await self.adapter.authenticate(role=preconditions.user_role)

        # Seed fixtures
        if preconditions.fixtures:
            fixtures_to_seed = []
            for fixture_id in preconditions.fixtures:
                if fixture_id in self.fixtures:
                    fixtures_to_seed.append(self.fixtures[fixture_id])

            if fixtures_to_seed:
                self._fixture_data = await self.adapter.seed(fixtures_to_seed)

        # Navigate to starting view
        if preconditions.view:
            url = self.adapter.resolve_view_url(preconditions.view)
            await self.page.goto(url)

    async def _execute_step(self, step: FlowStep) -> None:
        """Execute a single flow step."""
        match step.kind:
            case FlowStepKind.NAVIGATE:
                await self._step_navigate(step)
            case FlowStepKind.FILL:
                await self._step_fill(step)
            case FlowStepKind.CLICK:
                await self._step_click(step)
            case FlowStepKind.WAIT:
                await self._step_wait(step)
            case FlowStepKind.ASSERT:
                await self._step_assert(step)
            case FlowStepKind.SNAPSHOT:
                await self._step_snapshot(step)
            case _:
                raise ValueError(f"Unknown step kind: {step.kind}")

    async def _step_navigate(self, step: FlowStep) -> None:
        """Execute a navigate step."""
        if not step.target:
            raise ValueError("Navigate step requires target")

        # Parse target to get view ID
        if step.target.startswith("view:"):
            view_id = step.target.split(":", 1)[1]
            url = self.adapter.resolve_view_url(view_id)
        else:
            url = step.target

        # Replace placeholders with fixture data
        for _fixture_id, data in self._fixture_data.items():
            if isinstance(data, dict) and "id" in data:
                url = url.replace("{id}", str(data["id"]))

        await self.page.goto(url)

    async def _step_fill(self, step: FlowStep) -> None:
        """Execute a fill step."""
        if not step.target:
            raise ValueError("Fill step requires target")

        # Get the locator
        locator = get_locator_for_target(self.locators, step.target)

        # Resolve the value
        value = self._resolve_value(step)

        # Fill the field
        await locator.fill(str(value))

    async def _step_click(self, step: FlowStep) -> None:
        """Execute a click step."""
        if not step.target:
            raise ValueError("Click step requires target")

        locator = get_locator_for_target(self.locators, step.target)
        await locator.click()

    async def _step_wait(self, step: FlowStep) -> None:
        """Execute a wait step."""
        if step.value:
            # Wait for specified time
            await self.page.wait_for_timeout(int(step.value))
        elif step.target:
            # Wait for element
            locator = get_locator_for_target(self.locators, step.target)
            await locator.wait_for(state="visible", timeout=self.default_timeout)
        else:
            # Default wait
            await self.page.wait_for_timeout(1000)

    async def _step_assert(self, step: FlowStep) -> None:
        """Execute an assert step."""
        if not step.assertion:
            raise ValueError("Assert step requires assertion")

        await self._execute_assertion(step.assertion)

    async def _step_snapshot(self, step: FlowStep) -> None:
        """Execute a snapshot step (capture database state)."""
        snapshot = await self.adapter.snapshot()
        # Store snapshot for later assertions
        self._fixture_data["__snapshot__"] = snapshot

    async def _execute_assertion(self, assertion: FlowAssertion) -> None:
        """Execute a flow assertion."""
        match assertion.kind:
            case FlowAssertionKind.ENTITY_EXISTS:
                await self.assertions.entity_exists(
                    assertion.target or "",
                    assertion.expected if isinstance(assertion.expected, dict) else None,
                )

            case FlowAssertionKind.ENTITY_NOT_EXISTS:
                await self.assertions.entity_not_exists(
                    assertion.target or "",
                    assertion.expected if isinstance(assertion.expected, dict) else None,
                )

            case FlowAssertionKind.VALIDATION_ERROR:
                target = assertion.target or ""
                if target.startswith("field:"):
                    target = target.split(":", 1)[1]
                await self.assertions.validation_error(target)

            case FlowAssertionKind.VISIBLE:
                target = assertion.target or ""
                if target.startswith("view:"):
                    view_id = target.split(":", 1)[1]
                    await self.assertions.view_visible(view_id)
                else:
                    locator = get_locator_for_target(self.locators, target)
                    await locator.wait_for(state="visible", timeout=self.default_timeout)

            case FlowAssertionKind.NOT_VISIBLE:
                target = assertion.target or ""
                if target.startswith("view:"):
                    view_id = target.split(":", 1)[1]
                    await self.assertions.view_not_visible(view_id)
                else:
                    locator = get_locator_for_target(self.locators, target)
                    await locator.wait_for(state="hidden", timeout=self.default_timeout)

            case FlowAssertionKind.TEXT_CONTAINS:
                await self.assertions.text_visible(str(assertion.expected))

            case FlowAssertionKind.REDIRECTS_TO:
                target = assertion.target or ""
                if target.startswith("view:"):
                    view_id = target.split(":", 1)[1]
                else:
                    view_id = target
                await self.assertions.redirected_to(view_id)

            case FlowAssertionKind.COUNT:
                target = assertion.target or ""
                expected = int(assertion.expected) if assertion.expected is not None else 0
                await self.assertions.entity_count(target, expected)

            case FlowAssertionKind.FIELD_VALUE:
                target = assertion.target or ""
                if target.startswith("field:"):
                    target = target.split(":", 1)[1]
                await self.assertions.field_value(target, assertion.expected)

            case _:
                raise ValueError(f"Unknown assertion kind: {assertion.kind}")

    def _resolve_value(self, step: FlowStep) -> str | int | float | bool:
        """Resolve the value for a fill step."""
        if step.value is not None:
            return step.value

        if step.fixture_ref:
            # Parse fixture reference (e.g., "Task_valid.title")
            parts = step.fixture_ref.split(".")
            if len(parts) == 2:
                fixture_id, field_name = parts
                if fixture_id in self._fixture_data:
                    data = self._fixture_data[fixture_id]
                    if isinstance(data, dict) and field_name in data:
                        return data[field_name]

                # Fall back to fixture definition
                if fixture_id in self.fixtures:
                    fixture = self.fixtures[fixture_id]
                    if field_name in fixture.data:
                        return fixture.data[field_name]

        raise ValueError(f"Could not resolve value for step: {step}")


async def run_flow(
    page: "Page",
    flow: FlowSpec,
    adapter: "BaseAdapter",
    fixtures: dict[str, FixtureSpec] | None = None,
) -> FlowResult:
    """
    Convenience function to run a single flow.

    Args:
        page: Playwright Page instance
        flow: Flow specification to execute
        adapter: Stack adapter
        fixtures: Optional fixtures dict

    Returns:
        FlowResult with pass/fail status
    """
    async with FlowRunner(page, adapter, fixtures) as runner:
        return await runner.run_flow(flow)


async def run_testspec(
    page: "Page",
    testspec: E2ETestSpec,
    adapter: "BaseAdapter",
    priority_filter: str | None = None,
    tag_filter: str | None = None,
) -> list[FlowResult]:
    """
    Run all flows in an E2ETestSpec.

    Args:
        page: Playwright Page instance
        testspec: Complete test specification
        adapter: Stack adapter
        priority_filter: Optional priority filter (high, medium, low)
        tag_filter: Optional tag filter

    Returns:
        List of FlowResults for all flows
    """
    from dazzle.core.ir import FlowPriority

    # Build fixtures dict
    fixtures = {f.id: f for f in testspec.fixtures}

    # Filter flows
    flows = testspec.flows

    if priority_filter:
        priority = FlowPriority(priority_filter)
        flows = [f for f in flows if f.priority == priority]

    if tag_filter:
        flows = [f for f in flows if tag_filter in f.tags]

    # Run each flow
    results: list[FlowResult] = []
    for flow in flows:
        async with FlowRunner(page, adapter, fixtures) as runner:
            result = await runner.run_flow(flow)
            results.append(result)

    return results
