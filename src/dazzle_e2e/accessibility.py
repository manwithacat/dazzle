"""
Accessibility Testing Module for Dazzle E2E Testing.

Integrates axe-core for WCAG compliance checking and maps violations
back to AppSpec elements for actionable feedback.

Usage:
    from dazzle_e2e.accessibility import AccessibilityChecker

    checker = AccessibilityChecker(page)
    results = await checker.run_axe()
    for violation in results.violations:
        print(f"{violation.id}: {violation.impact} - {violation.description}")
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import A11yRule, E2ETestSpec

if TYPE_CHECKING:
    from playwright.async_api import Page

# axe-core script (minified version loaded via CDN)
AXE_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.3/axe.min.js"


@dataclass
class AxeNode:
    """A single DOM node identified in an accessibility violation."""

    html: str
    target: list[str]  # CSS selectors to locate the node
    failure_summary: str | None = None

    # Dazzle semantic info (populated by mapping)
    dazzle_entity: str | None = None
    dazzle_field: str | None = None
    dazzle_action: str | None = None
    dazzle_view: str | None = None


@dataclass
class AxeViolation:
    """A single accessibility violation from axe-core."""

    id: str  # Rule ID (e.g., "color-contrast")
    impact: str  # "critical", "serious", "moderate", "minor"
    description: str
    help: str
    help_url: str
    tags: list[str]  # e.g., ["wcag2a", "wcag2aa"]
    nodes: list[AxeNode] = field(default_factory=list)

    @property
    def wcag_level(self) -> str | None:
        """Get WCAG level from tags."""
        for tag in self.tags:
            if tag.startswith("wcag"):
                if "wcag2aaa" in tag or "wcag21aaa" in tag or "wcag22aaa" in tag:
                    return "AAA"
                elif "wcag2aa" in tag or "wcag21aa" in tag or "wcag22aa" in tag:
                    return "AA"
                elif "wcag2a" in tag or "wcag21a" in tag or "wcag22a" in tag:
                    return "A"
        return None

    @property
    def is_wcag(self) -> bool:
        """Check if this is a WCAG-related violation."""
        return any(tag.startswith("wcag") for tag in self.tags)


@dataclass
class AxePass:
    """An accessibility rule that passed."""

    id: str
    description: str
    help: str


@dataclass
class AxeResults:
    """Complete results from an axe-core analysis."""

    violations: list[AxeViolation] = field(default_factory=list)
    passes: list[AxePass] = field(default_factory=list)
    incomplete: list[AxeViolation] = field(default_factory=list)  # Needs manual review
    url: str | None = None
    timestamp: str | None = None

    @property
    def passed(self) -> bool:
        """Check if there are no violations."""
        return len(self.violations) == 0

    @property
    def critical_count(self) -> int:
        """Count of critical violations."""
        return sum(1 for v in self.violations if v.impact == "critical")

    @property
    def serious_count(self) -> int:
        """Count of serious violations."""
        return sum(1 for v in self.violations if v.impact == "serious")

    @property
    def wcag_a_violations(self) -> list[AxeViolation]:
        """Get WCAG Level A violations."""
        return [v for v in self.violations if v.wcag_level == "A"]

    @property
    def wcag_aa_violations(self) -> list[AxeViolation]:
        """Get WCAG Level AA violations."""
        return [v for v in self.violations if v.wcag_level == "AA"]


class AccessibilityChecker:
    """
    Accessibility checker using axe-core.

    Runs axe-core in the browser to check WCAG compliance and
    maps violations back to Dazzle semantic elements.
    """

    def __init__(
        self,
        page: "Page",
        rules: list[A11yRule] | None = None,
    ) -> None:
        """
        Initialize the accessibility checker.

        Args:
            page: Playwright Page instance
            rules: Optional A11y rules to filter checks
        """
        self.page = page
        self.rules = rules or []
        self._axe_loaded = False

        # Build rule config from A11yRule list
        self._enabled_rules: set[str] = set()
        self._disabled_rules: set[str] = set()
        self._level_filter: str | None = None

        for rule in self.rules:
            if rule.enabled:
                self._enabled_rules.add(rule.id)
            else:
                self._disabled_rules.add(rule.id)

    async def _ensure_axe_loaded(self) -> None:
        """Load axe-core into the page if not already loaded."""
        if self._axe_loaded:
            return

        # Check if axe is already available
        has_axe = await self.page.evaluate("typeof window.axe !== 'undefined'")
        if has_axe:
            self._axe_loaded = True
            return

        # Load axe-core from CDN
        await self.page.add_script_tag(url=AXE_CDN_URL)

        # Wait for axe to be available
        await self.page.wait_for_function("typeof window.axe !== 'undefined'", timeout=10000)
        self._axe_loaded = True

    async def run_axe(
        self,
        context: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AxeResults:
        """
        Run axe-core accessibility analysis.

        Args:
            context: Optional CSS selector to scope the analysis
            options: Optional axe-core options

        Returns:
            AxeResults with violations and passes
        """
        await self._ensure_axe_loaded()

        # Build options
        axe_options = options or {}

        # Apply rule filters
        if self._enabled_rules or self._disabled_rules:
            rules_config = {}
            for rule_id in self._enabled_rules:
                rules_config[rule_id] = {"enabled": True}
            for rule_id in self._disabled_rules:
                rules_config[rule_id] = {"enabled": False}
            axe_options["rules"] = rules_config

        # Run axe-core
        if context:
            results = await self.page.evaluate(
                f"""
                async () => {{
                    const options = {repr(axe_options)};
                    return await axe.run('{context}', options);
                }}
                """
            )
        else:
            results = await self.page.evaluate(
                f"""
                async () => {{
                    const options = {repr(axe_options)};
                    return await axe.run(document, options);
                }}
                """
            )

        return self._parse_results(results)

    async def check_wcag_level(
        self,
        level: str = "AA",
        context: str | None = None,
    ) -> AxeResults:
        """
        Check compliance at a specific WCAG level.

        Args:
            level: WCAG level ("A", "AA", or "AAA")
            context: Optional CSS selector to scope the analysis

        Returns:
            AxeResults with violations at or above the specified level
        """
        # Map levels to axe-core tags
        level_tags = {
            "A": ["wcag2a", "wcag21a", "wcag22a"],
            "AA": ["wcag2a", "wcag21a", "wcag22a", "wcag2aa", "wcag21aa", "wcag22aa"],
            "AAA": [
                "wcag2a",
                "wcag21a",
                "wcag22a",
                "wcag2aa",
                "wcag21aa",
                "wcag22aa",
                "wcag2aaa",
                "wcag21aaa",
                "wcag22aaa",
            ],
        }

        tags = level_tags.get(level.upper(), level_tags["AA"])
        options = {"runOnly": {"type": "tag", "values": tags}}

        return await self.run_axe(context=context, options=options)

    async def check_rule(
        self,
        rule_id: str,
        context: str | None = None,
    ) -> AxeResults:
        """
        Check a specific accessibility rule.

        Args:
            rule_id: The axe-core rule ID (e.g., "color-contrast")
            context: Optional CSS selector to scope the analysis

        Returns:
            AxeResults for the specific rule
        """
        options = {"runOnly": {"type": "rule", "values": [rule_id]}}
        return await self.run_axe(context=context, options=options)

    def _parse_results(self, results: dict[str, Any]) -> AxeResults:
        """Parse raw axe-core results into AxeResults."""
        violations = []
        for v in results.get("violations", []):
            nodes = []
            for node in v.get("nodes", []):
                nodes.append(
                    AxeNode(
                        html=node.get("html", ""),
                        target=node.get("target", []),
                        failure_summary=node.get("failureSummary"),
                    )
                )

            violations.append(
                AxeViolation(
                    id=v.get("id", ""),
                    impact=v.get("impact", "minor"),
                    description=v.get("description", ""),
                    help=v.get("help", ""),
                    help_url=v.get("helpUrl", ""),
                    tags=v.get("tags", []),
                    nodes=nodes,
                )
            )

        passes = []
        for p in results.get("passes", []):
            passes.append(
                AxePass(
                    id=p.get("id", ""),
                    description=p.get("description", ""),
                    help=p.get("help", ""),
                )
            )

        incomplete = []
        for i in results.get("incomplete", []):
            nodes = []
            for node in i.get("nodes", []):
                nodes.append(
                    AxeNode(
                        html=node.get("html", ""),
                        target=node.get("target", []),
                        failure_summary=node.get("failureSummary"),
                    )
                )

            incomplete.append(
                AxeViolation(
                    id=i.get("id", ""),
                    impact=i.get("impact", "minor"),
                    description=i.get("description", ""),
                    help=i.get("help", ""),
                    help_url=i.get("helpUrl", ""),
                    tags=i.get("tags", []),
                    nodes=nodes,
                )
            )

        return AxeResults(
            violations=violations,
            passes=passes,
            incomplete=incomplete,
            url=results.get("url"),
            timestamp=results.get("timestamp"),
        )

    async def map_to_dazzle(self, results: AxeResults) -> AxeResults:
        """
        Map axe-core violations to Dazzle semantic elements.

        Enriches violation nodes with Dazzle entity, field, action, or view
        information when the violated element has semantic attributes.

        Args:
            results: AxeResults to enrich

        Returns:
            AxeResults with Dazzle mappings added
        """
        for violation in results.violations:
            for node in violation.nodes:
                await self._map_node_to_dazzle(node)

        for incomplete in results.incomplete:
            for node in incomplete.nodes:
                await self._map_node_to_dazzle(node)

        return results

    async def _map_node_to_dazzle(self, node: AxeNode) -> None:
        """Map a single node to Dazzle semantic info."""
        if not node.target:
            return

        # Use the first selector
        selector = node.target[0]

        try:
            element = self.page.locator(selector).first

            # Try to get Dazzle attributes
            node.dazzle_entity = await element.get_attribute("data-dazzle-entity")
            node.dazzle_field = await element.get_attribute("data-dazzle-field")
            node.dazzle_action = await element.get_attribute("data-dazzle-action")
            node.dazzle_view = await element.get_attribute("data-dazzle-view")

            # If not directly on element, check ancestors
            if not any(
                [node.dazzle_entity, node.dazzle_field, node.dazzle_action, node.dazzle_view]
            ):
                # Look for nearest Dazzle ancestor
                ancestor_info = await self.page.evaluate(
                    """
                    (selector) => {
                        const el = document.querySelector(selector);
                        if (!el) return null;

                        let current = el.parentElement;
                        while (current && current !== document.body) {
                            const entity = current.getAttribute('data-dazzle-entity');
                            const field = current.getAttribute('data-dazzle-field');
                            const action = current.getAttribute('data-dazzle-action');
                            const view = current.getAttribute('data-dazzle-view');

                            if (entity || field || action || view) {
                                return { entity, field, action, view };
                            }
                            current = current.parentElement;
                        }
                        return null;
                    }
                    """,
                    selector,
                )

                if ancestor_info:
                    node.dazzle_entity = ancestor_info.get("entity")
                    node.dazzle_field = ancestor_info.get("field")
                    node.dazzle_action = ancestor_info.get("action")
                    node.dazzle_view = ancestor_info.get("view")

        except Exception:
            pass  # Element may not exist anymore


@dataclass
class A11yCheckResult:
    """Result of accessibility checking with Dazzle context."""

    passed: bool
    axe_results: AxeResults
    violations_by_entity: dict[str, list[AxeViolation]] = field(default_factory=dict)
    violations_by_view: dict[str, list[AxeViolation]] = field(default_factory=dict)
    unmapped_violations: list[AxeViolation] = field(default_factory=list)

    @property
    def total_violations(self) -> int:
        """Total number of violations."""
        return len(self.axe_results.violations)

    @property
    def critical_errors(self) -> int:
        """Count of critical violations."""
        return self.axe_results.critical_count


def check_a11y_rules(results: AxeResults, rules: list[A11yRule]) -> list[AxeViolation]:
    """
    Filter axe results based on A11yRules from E2ETestSpec.

    Args:
        results: Raw axe-core results
        rules: A11y rules defining which checks to enforce

    Returns:
        List of violations for enabled rules
    """
    enabled_rule_ids = {r.id for r in rules if r.enabled}

    if not enabled_rule_ids:
        # If no rules specified, return all violations
        return results.violations

    return [v for v in results.violations if v.id in enabled_rule_ids]


async def run_accessibility_check(
    page: "Page",
    testspec: E2ETestSpec | None = None,
    level: str = "AA",
) -> A11yCheckResult:
    """
    Convenience function to run accessibility checks.

    Args:
        page: Playwright Page instance
        testspec: Optional E2ETestSpec for rule filtering
        level: WCAG level to check ("A", "AA", "AAA")

    Returns:
        A11yCheckResult with violations mapped to Dazzle elements
    """
    rules = testspec.a11y_rules if testspec else []
    checker = AccessibilityChecker(page, rules)

    # Run the check
    results = await checker.check_wcag_level(level)

    # Map to Dazzle elements
    results = await checker.map_to_dazzle(results)

    # Filter by rules if provided
    if rules:
        filtered_violations = check_a11y_rules(results, rules)
        results = AxeResults(
            violations=filtered_violations,
            passes=results.passes,
            incomplete=results.incomplete,
            url=results.url,
            timestamp=results.timestamp,
        )

    # Organize violations by entity and view
    violations_by_entity: dict[str, list[AxeViolation]] = {}
    violations_by_view: dict[str, list[AxeViolation]] = {}
    unmapped: list[AxeViolation] = []

    for violation in results.violations:
        has_mapping = False
        for node in violation.nodes:
            if node.dazzle_entity:
                has_mapping = True
                if node.dazzle_entity not in violations_by_entity:
                    violations_by_entity[node.dazzle_entity] = []
                if violation not in violations_by_entity[node.dazzle_entity]:
                    violations_by_entity[node.dazzle_entity].append(violation)

            if node.dazzle_view:
                has_mapping = True
                if node.dazzle_view not in violations_by_view:
                    violations_by_view[node.dazzle_view] = []
                if violation not in violations_by_view[node.dazzle_view]:
                    violations_by_view[node.dazzle_view].append(violation)

        if not has_mapping:
            unmapped.append(violation)

    return A11yCheckResult(
        passed=results.passed,
        axe_results=results,
        violations_by_entity=violations_by_entity,
        violations_by_view=violations_by_view,
        unmapped_violations=unmapped,
    )
