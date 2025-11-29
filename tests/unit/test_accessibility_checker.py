"""Unit tests for accessibility checking module."""

from dazzle.core.ir import A11yRule
from dazzle_e2e.accessibility import (
    A11yCheckResult,
    AccessibilityChecker,
    AxeNode,
    AxeResults,
    AxeViolation,
    check_a11y_rules,
)

# =============================================================================
# AxeViolation Tests
# =============================================================================


class TestAxeViolation:
    """Tests for AxeViolation dataclass."""

    def test_wcag_level_a(self):
        """Detect WCAG Level A."""
        violation = AxeViolation(
            id="link-name",
            impact="serious",
            description="Links must have discernible text",
            help="Links must have discernible text",
            help_url="https://dequeuniversity.com/rules/axe/4.8/link-name",
            tags=["cat.name-role-value", "wcag2a", "wcag412", "section508"],
        )

        assert violation.wcag_level == "A"
        assert violation.is_wcag

    def test_wcag_level_aa(self):
        """Detect WCAG Level AA."""
        violation = AxeViolation(
            id="color-contrast",
            impact="serious",
            description="Elements must meet minimum color contrast ratio",
            help="Elements must meet minimum color contrast ratio",
            help_url="https://dequeuniversity.com/rules/axe/4.8/color-contrast",
            tags=["cat.color", "wcag2aa", "wcag143"],
        )

        assert violation.wcag_level == "AA"
        assert violation.is_wcag

    def test_wcag_level_aaa(self):
        """Detect WCAG Level AAA."""
        violation = AxeViolation(
            id="color-contrast-enhanced",
            impact="serious",
            description="Elements must meet enhanced color contrast ratio",
            help="Elements must meet enhanced color contrast ratio",
            help_url="https://dequeuniversity.com/rules/axe/4.8/color-contrast-enhanced",
            tags=["cat.color", "wcag2aaa", "wcag146"],
        )

        assert violation.wcag_level == "AAA"
        assert violation.is_wcag

    def test_wcag21_tags(self):
        """Handle WCAG 2.1 specific tags."""
        violation = AxeViolation(
            id="target-size",
            impact="minor",
            description="Touch target size",
            help="Touch targets must be large enough",
            help_url="https://dequeuniversity.com/rules/axe/4.8/target-size",
            tags=["wcag21aa"],
        )

        assert violation.wcag_level == "AA"
        assert violation.is_wcag

    def test_non_wcag_violation(self):
        """Handle non-WCAG violations."""
        violation = AxeViolation(
            id="region",
            impact="moderate",
            description="All content should be contained in landmarks",
            help="All content should be contained by landmarks",
            help_url="https://dequeuniversity.com/rules/axe/4.8/region",
            tags=["cat.keyboard", "best-practice"],
        )

        assert violation.wcag_level is None
        assert not violation.is_wcag


# =============================================================================
# AxeResults Tests
# =============================================================================


class TestAxeResults:
    """Tests for AxeResults dataclass."""

    def test_passed_when_no_violations(self):
        """Results pass when no violations."""
        results = AxeResults(violations=[], passes=[])
        assert results.passed

    def test_failed_when_violations(self):
        """Results fail when violations exist."""
        violation = AxeViolation(
            id="test",
            impact="minor",
            description="Test",
            help="Test",
            help_url="",
            tags=[],
        )
        results = AxeResults(violations=[violation])
        assert not results.passed

    def test_critical_count(self):
        """Count critical violations."""
        violations = [
            AxeViolation(
                id="test1", impact="critical", description="", help="", help_url="", tags=[]
            ),
            AxeViolation(
                id="test2", impact="serious", description="", help="", help_url="", tags=[]
            ),
            AxeViolation(
                id="test3", impact="critical", description="", help="", help_url="", tags=[]
            ),
        ]

        results = AxeResults(violations=violations)
        assert results.critical_count == 2
        assert results.serious_count == 1

    def test_wcag_filtering(self):
        """Filter violations by WCAG level."""
        violations = [
            AxeViolation(
                id="a1", impact="serious", description="", help="", help_url="", tags=["wcag2a"]
            ),
            AxeViolation(
                id="a2", impact="serious", description="", help="", help_url="", tags=["wcag2a"]
            ),
            AxeViolation(
                id="aa1", impact="serious", description="", help="", help_url="", tags=["wcag2aa"]
            ),
            AxeViolation(
                id="bp",
                impact="minor",
                description="",
                help="",
                help_url="",
                tags=["best-practice"],
            ),
        ]

        results = AxeResults(violations=violations)

        assert len(results.wcag_a_violations) == 2
        assert len(results.wcag_aa_violations) == 1


# =============================================================================
# AxeNode Tests
# =============================================================================


class TestAxeNode:
    """Tests for AxeNode dataclass."""

    def test_node_with_dazzle_mapping(self):
        """Node with Dazzle semantic info."""
        node = AxeNode(
            html='<input type="text" data-dazzle-field="Task.title">',
            target=["[data-dazzle-field='Task.title']"],
            failure_summary="Fix form field",
            dazzle_entity="Task",
            dazzle_field="Task.title",
        )

        assert node.dazzle_entity == "Task"
        assert node.dazzle_field == "Task.title"
        assert node.dazzle_action is None

    def test_node_without_mapping(self):
        """Node without Dazzle semantic info."""
        node = AxeNode(
            html="<span>Some text</span>",
            target=["body > div > span"],
        )

        assert node.dazzle_entity is None
        assert node.dazzle_field is None


# =============================================================================
# check_a11y_rules Tests
# =============================================================================


class TestCheckA11yRules:
    """Tests for check_a11y_rules function."""

    def test_filter_by_enabled_rules(self):
        """Only return violations for enabled rules."""
        violations = [
            AxeViolation(
                id="color-contrast",
                impact="serious",
                description="Color contrast",
                help="",
                help_url="",
                tags=["wcag2aa"],
            ),
            AxeViolation(
                id="link-name",
                impact="serious",
                description="Link name",
                help="",
                help_url="",
                tags=["wcag2a"],
            ),
            AxeViolation(
                id="image-alt",
                impact="critical",
                description="Image alt",
                help="",
                help_url="",
                tags=["wcag2a"],
            ),
        ]

        results = AxeResults(violations=violations)

        rules = [
            A11yRule(id="color-contrast", level="AA", enabled=True),
            A11yRule(id="link-name", level="A", enabled=False),  # Disabled
            A11yRule(id="image-alt", level="A", enabled=True),
        ]

        filtered = check_a11y_rules(results, rules)

        assert len(filtered) == 2
        assert filtered[0].id == "color-contrast"
        assert filtered[1].id == "image-alt"

    def test_no_rules_returns_all(self):
        """No rules means return all violations."""
        violations = [
            AxeViolation(id="test1", impact="minor", description="", help="", help_url="", tags=[]),
            AxeViolation(id="test2", impact="minor", description="", help="", help_url="", tags=[]),
        ]

        results = AxeResults(violations=violations)
        filtered = check_a11y_rules(results, [])

        assert len(filtered) == 2

    def test_all_disabled_returns_empty(self):
        """All disabled rules means return empty."""
        violations = [
            AxeViolation(id="test1", impact="minor", description="", help="", help_url="", tags=[]),
        ]

        results = AxeResults(violations=violations)
        rules = [A11yRule(id="other-rule", level="A", enabled=True)]

        filtered = check_a11y_rules(results, rules)

        # test1 is not in enabled rules, so it's not returned
        assert len(filtered) == 0


# =============================================================================
# A11yCheckResult Tests
# =============================================================================


class TestA11yCheckResult:
    """Tests for A11yCheckResult dataclass."""

    def test_total_violations(self):
        """Count total violations."""
        violations = [
            AxeViolation(id="test1", impact="minor", description="", help="", help_url="", tags=[]),
            AxeViolation(
                id="test2", impact="critical", description="", help="", help_url="", tags=[]
            ),
        ]

        result = A11yCheckResult(
            passed=False,
            axe_results=AxeResults(violations=violations),
        )

        assert result.total_violations == 2
        assert result.critical_errors == 1

    def test_violations_by_entity(self):
        """Organize violations by entity."""
        task_violation = AxeViolation(
            id="label", impact="serious", description="", help="", help_url="", tags=[]
        )
        user_violation = AxeViolation(
            id="color-contrast", impact="serious", description="", help="", help_url="", tags=[]
        )

        result = A11yCheckResult(
            passed=False,
            axe_results=AxeResults(violations=[task_violation, user_violation]),
            violations_by_entity={
                "Task": [task_violation],
                "User": [user_violation],
            },
        )

        assert "Task" in result.violations_by_entity
        assert len(result.violations_by_entity["Task"]) == 1
        assert result.violations_by_entity["Task"][0].id == "label"


# =============================================================================
# AccessibilityChecker Initialization Tests
# =============================================================================


class TestAccessibilityCheckerInit:
    """Tests for AccessibilityChecker initialization (without browser)."""

    def test_init_with_rules(self):
        """Initialize with A11y rules."""
        rules = [
            A11yRule(id="color-contrast", level="AA", enabled=True),
            A11yRule(id="link-name", level="A", enabled=False),
        ]

        # Create checker without page (just testing initialization)
        checker = AccessibilityChecker(page=None, rules=rules)  # type: ignore

        assert len(checker._enabled_rules) == 1
        assert "color-contrast" in checker._enabled_rules
        assert len(checker._disabled_rules) == 1
        assert "link-name" in checker._disabled_rules

    def test_init_without_rules(self):
        """Initialize without rules."""
        checker = AccessibilityChecker(page=None)  # type: ignore

        assert len(checker._enabled_rules) == 0
        assert len(checker._disabled_rules) == 0


# =============================================================================
# Result Parsing Tests
# =============================================================================


class TestResultParsing:
    """Tests for parsing axe-core results."""

    def test_parse_violations(self):
        """Parse violations from raw results."""
        raw_results = {
            "violations": [
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "description": "Elements must meet minimum color contrast ratio",
                    "help": "Elements must meet minimum color contrast ratio",
                    "helpUrl": "https://dequeuniversity.com/rules/axe/4.8/color-contrast",
                    "tags": ["cat.color", "wcag2aa", "wcag143"],
                    "nodes": [
                        {
                            "html": '<span style="color: #777;">Low contrast</span>',
                            "target": ["body > span"],
                            "failureSummary": "Fix color contrast",
                        }
                    ],
                }
            ],
            "passes": [],
            "incomplete": [],
        }

        checker = AccessibilityChecker(page=None)  # type: ignore
        results = checker._parse_results(raw_results)

        assert len(results.violations) == 1
        assert results.violations[0].id == "color-contrast"
        assert results.violations[0].impact == "serious"
        assert len(results.violations[0].nodes) == 1
        assert results.violations[0].nodes[0].failure_summary == "Fix color contrast"

    def test_parse_passes(self):
        """Parse passes from raw results."""
        raw_results = {
            "violations": [],
            "passes": [
                {
                    "id": "button-name",
                    "description": "Buttons must have discernible text",
                    "help": "Buttons must have discernible text",
                }
            ],
            "incomplete": [],
        }

        checker = AccessibilityChecker(page=None)  # type: ignore
        results = checker._parse_results(raw_results)

        assert len(results.passes) == 1
        assert results.passes[0].id == "button-name"

    def test_parse_incomplete(self):
        """Parse incomplete checks from raw results."""
        raw_results = {
            "violations": [],
            "passes": [],
            "incomplete": [
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "description": "Needs review",
                    "help": "Check manually",
                    "helpUrl": "",
                    "tags": ["wcag2aa"],
                    "nodes": [],
                }
            ],
        }

        checker = AccessibilityChecker(page=None)  # type: ignore
        results = checker._parse_results(raw_results)

        assert len(results.incomplete) == 1
        assert results.incomplete[0].id == "color-contrast"
