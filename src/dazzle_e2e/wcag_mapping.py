"""
WCAG Violation Mapping for Dazzle E2E Testing.

Maps axe-core accessibility violations back to AppSpec elements
(entities, fields, surfaces, workspaces) for actionable feedback.

Usage:
    from dazzle_e2e.wcag_mapping import WCAGMapper, map_violations_to_appspec

    mapper = WCAGMapper(appspec)
    mapped = mapper.map_violations(a11y_results.violations)
    for item in mapped:
        print(f"Fix {item.wcag_criterion} in {item.appspec_location}")
"""

from dataclasses import dataclass, field

from dazzle.core.ir import AppSpec, EntitySpec, SurfaceSpec, WorkspaceSpec
from dazzle_e2e.accessibility import AxeViolation

# WCAG 2.1 Criteria mapping
WCAG_CRITERIA = {
    # Level A
    "1.1.1": {
        "name": "Non-text Content",
        "level": "A",
        "description": "All non-text content has a text alternative",
    },
    "1.3.1": {
        "name": "Info and Relationships",
        "level": "A",
        "description": "Information and structure can be programmatically determined",
    },
    "1.4.1": {
        "name": "Use of Color",
        "level": "A",
        "description": "Color is not the only visual means of conveying information",
    },
    "2.1.1": {
        "name": "Keyboard",
        "level": "A",
        "description": "All functionality is operable through a keyboard",
    },
    "2.4.1": {
        "name": "Bypass Blocks",
        "level": "A",
        "description": "A mechanism is available to bypass repeated content",
    },
    "2.4.2": {
        "name": "Page Titled",
        "level": "A",
        "description": "Web pages have titles that describe topic or purpose",
    },
    "2.4.4": {
        "name": "Link Purpose (In Context)",
        "level": "A",
        "description": "Link purpose can be determined from link text or context",
    },
    "3.1.1": {
        "name": "Language of Page",
        "level": "A",
        "description": "Default human language can be programmatically determined",
    },
    "3.3.1": {
        "name": "Error Identification",
        "level": "A",
        "description": "Input errors are identified and described in text",
    },
    "3.3.2": {
        "name": "Labels or Instructions",
        "level": "A",
        "description": "Labels or instructions are provided for user input",
    },
    "4.1.1": {
        "name": "Parsing",
        "level": "A",
        "description": "Elements have complete start and end tags, no duplicates",
    },
    "4.1.2": {
        "name": "Name, Role, Value",
        "level": "A",
        "description": "Name and role can be programmatically determined",
    },
    # Level AA
    "1.3.4": {
        "name": "Orientation",
        "level": "AA",
        "description": "Content not restricted to single display orientation",
    },
    "1.3.5": {
        "name": "Identify Input Purpose",
        "level": "AA",
        "description": "Input purpose can be programmatically determined",
    },
    "1.4.3": {
        "name": "Contrast (Minimum)",
        "level": "AA",
        "description": "Text has minimum 4.5:1 contrast ratio",
    },
    "1.4.4": {
        "name": "Resize Text",
        "level": "AA",
        "description": "Text can be resized to 200% without loss of functionality",
    },
    "1.4.10": {
        "name": "Reflow",
        "level": "AA",
        "description": "Content can reflow at 320px width without horizontal scroll",
    },
    "1.4.11": {
        "name": "Non-text Contrast",
        "level": "AA",
        "description": "UI components have 3:1 contrast with adjacent colors",
    },
    "1.4.12": {
        "name": "Text Spacing",
        "level": "AA",
        "description": "No loss of content when text spacing is adjusted",
    },
    "2.4.6": {
        "name": "Headings and Labels",
        "level": "AA",
        "description": "Headings and labels describe topic or purpose",
    },
    "2.4.7": {
        "name": "Focus Visible",
        "level": "AA",
        "description": "Keyboard focus indicator is visible",
    },
    "3.2.3": {
        "name": "Consistent Navigation",
        "level": "AA",
        "description": "Navigation repeated on pages occurs in the same order",
    },
    "3.2.4": {
        "name": "Consistent Identification",
        "level": "AA",
        "description": "Components with same functionality identified consistently",
    },
    "3.3.3": {
        "name": "Error Suggestion",
        "level": "AA",
        "description": "Known input error suggestions are provided",
    },
    "3.3.4": {
        "name": "Error Prevention (Legal, Financial, Data)",
        "level": "AA",
        "description": "Submissions are reversible, checked, or confirmed",
    },
}

# Mapping from axe rule IDs to WCAG criteria
AXE_TO_WCAG: dict[str, list[str]] = {
    "image-alt": ["1.1.1"],
    "input-image-alt": ["1.1.1"],
    "object-alt": ["1.1.1"],
    "area-alt": ["1.1.1"],
    "svg-img-alt": ["1.1.1"],
    "label": ["1.3.1", "3.3.2"],
    "label-title-only": ["1.3.1"],
    "form-field-multiple-labels": ["1.3.1"],
    "aria-required-attr": ["1.3.1", "4.1.2"],
    "aria-required-children": ["1.3.1"],
    "aria-required-parent": ["1.3.1"],
    "definition-list": ["1.3.1"],
    "dlitem": ["1.3.1"],
    "list": ["1.3.1"],
    "listitem": ["1.3.1"],
    "th-has-data-cells": ["1.3.1"],
    "td-has-header": ["1.3.1"],
    "table-fake-caption": ["1.3.1"],
    "p-as-heading": ["1.3.1"],
    "link-in-text-block": ["1.4.1"],
    "color-contrast": ["1.4.3"],
    "color-contrast-enhanced": ["1.4.6"],
    "bypass": ["2.4.1"],
    "document-title": ["2.4.2"],
    "link-name": ["2.4.4"],
    "button-name": ["4.1.2"],
    "html-has-lang": ["3.1.1"],
    "html-lang-valid": ["3.1.1"],
    "valid-lang": ["3.1.2"],
    "autocomplete-valid": ["1.3.5"],
    "focus-visible": ["2.4.7"],
    "focus-order-semantics": ["2.4.3"],
    "heading-order": ["1.3.1", "2.4.6"],
    "empty-heading": ["2.4.6"],
    "duplicate-id": ["4.1.1"],
    "duplicate-id-active": ["4.1.1"],
    "duplicate-id-aria": ["4.1.1"],
    "aria-valid-attr": ["4.1.2"],
    "aria-valid-attr-value": ["4.1.2"],
    "aria-roles": ["4.1.2"],
    "aria-hidden-body": ["4.1.2"],
    "aria-hidden-focus": ["4.1.2"],
    "role-img-alt": ["1.1.1"],
    "scrollable-region-focusable": ["2.1.1"],
    "nested-interactive": ["4.1.2"],
    "select-name": ["4.1.2"],
    "input-button-name": ["4.1.2"],
    "frame-title": ["2.4.1", "4.1.2"],
    "frame-focusable-content": ["2.1.1"],
    "skip-link": ["2.4.1"],
    "tabindex": ["2.1.1"],
    "accesskeys": ["2.4.1"],
}


@dataclass
class WCAGViolationMapping:
    """A mapped WCAG violation with AppSpec context."""

    violation: AxeViolation
    wcag_criterion: str
    wcag_name: str
    wcag_level: str
    wcag_description: str

    # AppSpec location (if mapped)
    entity_name: str | None = None
    field_name: str | None = None
    surface_name: str | None = None
    workspace_name: str | None = None

    # Fix suggestion
    suggested_fix: str | None = None
    appspec_location: str | None = None

    @property
    def has_mapping(self) -> bool:
        """Check if violation is mapped to AppSpec."""
        return any([self.entity_name, self.field_name, self.surface_name, self.workspace_name])


@dataclass
class WCAGMappingResult:
    """Result of mapping violations to AppSpec."""

    mapped_violations: list[WCAGViolationMapping] = field(default_factory=list)
    by_entity: dict[str, list[WCAGViolationMapping]] = field(default_factory=dict)
    by_surface: dict[str, list[WCAGViolationMapping]] = field(default_factory=dict)
    by_workspace: dict[str, list[WCAGViolationMapping]] = field(default_factory=dict)
    by_criterion: dict[str, list[WCAGViolationMapping]] = field(default_factory=dict)
    unmapped: list[WCAGViolationMapping] = field(default_factory=list)

    @property
    def total_violations(self) -> int:
        """Total number of violations."""
        return len(self.mapped_violations)

    @property
    def mapped_count(self) -> int:
        """Number of violations mapped to AppSpec."""
        return sum(1 for v in self.mapped_violations if v.has_mapping)


class WCAGMapper:
    """
    Maps axe-core violations to AppSpec elements.

    Provides actionable feedback by identifying which AppSpec elements
    (entities, fields, surfaces, workspaces) need accessibility fixes.
    """

    def __init__(self, appspec: AppSpec) -> None:
        """
        Initialize the WCAG mapper.

        Args:
            appspec: The application specification
        """
        self.appspec = appspec
        self._entity_index = self._build_entity_index()
        self._surface_index = self._build_surface_index()
        self._workspace_index = self._build_workspace_index()

    def _build_entity_index(self) -> dict[str, EntitySpec]:
        """Build index of entities by name."""
        return {e.name: e for e in self.appspec.domain.entities}

    def _build_surface_index(self) -> dict[str, SurfaceSpec]:
        """Build index of surfaces by name."""
        return {s.name: s for s in self.appspec.surfaces}

    def _build_workspace_index(self) -> dict[str, WorkspaceSpec]:
        """Build index of workspaces by name."""
        return {w.name: w for w in self.appspec.workspaces}

    def map_violations(
        self,
        violations: list[AxeViolation],
    ) -> WCAGMappingResult:
        """
        Map violations to AppSpec elements.

        Args:
            violations: List of axe-core violations

        Returns:
            WCAGMappingResult with mapped violations
        """
        result = WCAGMappingResult()

        for violation in violations:
            mappings = self._map_violation(violation)
            result.mapped_violations.extend(mappings)

            for mapping in mappings:
                # Index by criterion
                if mapping.wcag_criterion not in result.by_criterion:
                    result.by_criterion[mapping.wcag_criterion] = []
                result.by_criterion[mapping.wcag_criterion].append(mapping)

                # Index by AppSpec location
                if mapping.entity_name:
                    if mapping.entity_name not in result.by_entity:
                        result.by_entity[mapping.entity_name] = []
                    result.by_entity[mapping.entity_name].append(mapping)

                if mapping.surface_name:
                    if mapping.surface_name not in result.by_surface:
                        result.by_surface[mapping.surface_name] = []
                    result.by_surface[mapping.surface_name].append(mapping)

                if mapping.workspace_name:
                    if mapping.workspace_name not in result.by_workspace:
                        result.by_workspace[mapping.workspace_name] = []
                    result.by_workspace[mapping.workspace_name].append(mapping)

                if not mapping.has_mapping:
                    result.unmapped.append(mapping)

        return result

    def _map_violation(self, violation: AxeViolation) -> list[WCAGViolationMapping]:
        """Map a single violation to WCAG criteria and AppSpec."""
        mappings = []

        # Get WCAG criteria for this rule
        wcag_criteria = AXE_TO_WCAG.get(violation.id, [])

        # If no mapping, use tags to infer criteria
        if not wcag_criteria:
            wcag_criteria = self._criteria_from_tags(violation.tags)

        # Create a mapping for each criterion
        for criterion in wcag_criteria or ["unknown"]:
            criterion_info = WCAG_CRITERIA.get(
                criterion,
                {"name": "Unknown", "level": "?", "description": violation.description},
            )

            # Map to AppSpec based on node info
            entity_name = None
            field_name = None
            surface_name = None
            workspace_name = None
            appspec_location = None

            for node in violation.nodes:
                if node.dazzle_entity:
                    entity_name = node.dazzle_entity
                if node.dazzle_field:
                    field_name = node.dazzle_field
                if node.dazzle_view:
                    # Check if it's a surface or workspace
                    if node.dazzle_view in self._surface_index:
                        surface_name = node.dazzle_view
                    elif node.dazzle_view in self._workspace_index:
                        workspace_name = node.dazzle_view

            # Build AppSpec location string
            if entity_name and field_name:
                appspec_location = f"entity:{entity_name}.{field_name}"
            elif entity_name:
                appspec_location = f"entity:{entity_name}"
            elif surface_name:
                appspec_location = f"surface:{surface_name}"
            elif workspace_name:
                appspec_location = f"workspace:{workspace_name}"

            # Generate fix suggestion
            suggested_fix = self._suggest_fix(violation, criterion, entity_name, field_name)

            mappings.append(
                WCAGViolationMapping(
                    violation=violation,
                    wcag_criterion=criterion,
                    wcag_name=criterion_info["name"],
                    wcag_level=criterion_info["level"],
                    wcag_description=criterion_info["description"],
                    entity_name=entity_name,
                    field_name=field_name,
                    surface_name=surface_name,
                    workspace_name=workspace_name,
                    suggested_fix=suggested_fix,
                    appspec_location=appspec_location,
                )
            )

        return mappings if mappings else [self._create_unmapped(violation)]

    def _criteria_from_tags(self, tags: list[str]) -> list[str]:
        """Extract WCAG criteria from axe tags."""
        criteria = []
        for tag in tags:
            # Tags like "wcag143" map to "1.4.3"
            if tag.startswith("wcag") and not tag.endswith(("a", "aa", "aaa")):
                # Extract number part
                num = tag.replace("wcag", "").replace("21", "").replace("22", "")
                if len(num) == 3:
                    criteria.append(f"{num[0]}.{num[1]}.{num[2]}")
                elif len(num) == 4:
                    criteria.append(f"{num[0]}.{num[1]}.{num[2:]}")
        return criteria

    def _create_unmapped(self, violation: AxeViolation) -> WCAGViolationMapping:
        """Create an unmapped violation entry."""
        return WCAGViolationMapping(
            violation=violation,
            wcag_criterion="unknown",
            wcag_name="Unknown",
            wcag_level="?",
            wcag_description=violation.description,
            suggested_fix=violation.help,
        )

    def _suggest_fix(
        self,
        violation: AxeViolation,
        criterion: str,
        entity_name: str | None,
        field_name: str | None,
    ) -> str:
        """Generate a fix suggestion for the violation."""
        suggestions: dict[str, str] = {
            "color-contrast": "Increase color contrast ratio to at least 4.5:1 for text. "
            "Consider using darker text colors or lighter backgrounds.",
            "label": f"Add a label for the {'field ' + field_name if field_name else 'form field'}. "
            "In DSL, ensure the field has a display_name or label defined.",
            "button-name": "Add accessible text to the button. "
            "Use aria-label or visible text content.",
            "link-name": "Add accessible text to the link. "
            "Ensure links have descriptive text, not just 'click here'.",
            "image-alt": "Add alt text to the image. "
            "Describe the image content or use empty alt for decorative images.",
            "heading-order": "Fix heading hierarchy. "
            "Ensure headings follow sequential order (h1, h2, h3, etc.).",
            "focus-visible": "Ensure focus indicator is visible. "
            "Add focus styles to interactive elements.",
            "duplicate-id": "Remove duplicate ID attributes. Each ID must be unique on the page.",
        }

        # Get specific suggestion or fall back to violation help
        return suggestions.get(violation.id, violation.help)


def map_violations_to_appspec(
    violations: list[AxeViolation],
    appspec: AppSpec,
) -> WCAGMappingResult:
    """
    Convenience function to map violations to AppSpec.

    Args:
        violations: List of axe-core violations
        appspec: Application specification

    Returns:
        WCAGMappingResult with mapped violations
    """
    mapper = WCAGMapper(appspec)
    return mapper.map_violations(violations)


def format_violation_report(result: WCAGMappingResult) -> str:
    """
    Format violation mapping result as a human-readable report.

    Args:
        result: WCAG mapping result

    Returns:
        Formatted string report
    """
    lines = []
    lines.append("=" * 60)
    lines.append("WCAG Accessibility Violation Report")
    lines.append("=" * 60)
    lines.append(f"Total violations: {result.total_violations}")
    lines.append(f"Mapped to AppSpec: {result.mapped_count}")
    lines.append(f"Unmapped: {len(result.unmapped)}")
    lines.append("")

    # By criterion
    if result.by_criterion:
        lines.append("-" * 40)
        lines.append("Violations by WCAG Criterion:")
        lines.append("-" * 40)
        for criterion, mappings in sorted(result.by_criterion.items()):
            if mappings:
                lines.append(
                    f"  {criterion} ({mappings[0].wcag_name}) - {len(mappings)} violation(s)"
                )

    # By entity
    if result.by_entity:
        lines.append("")
        lines.append("-" * 40)
        lines.append("Violations by Entity:")
        lines.append("-" * 40)
        for entity, mappings in sorted(result.by_entity.items()):
            lines.append(f"  {entity}:")
            for mapping in mappings:
                lines.append(f"    - {mapping.wcag_criterion}: {mapping.violation.id}")
                if mapping.suggested_fix:
                    lines.append(f"      Fix: {mapping.suggested_fix[:80]}...")

    # By surface
    if result.by_surface:
        lines.append("")
        lines.append("-" * 40)
        lines.append("Violations by Surface:")
        lines.append("-" * 40)
        for surface, mappings in sorted(result.by_surface.items()):
            lines.append(f"  {surface}: {len(mappings)} violation(s)")

    # Unmapped
    if result.unmapped:
        lines.append("")
        lines.append("-" * 40)
        lines.append("Unmapped Violations:")
        lines.append("-" * 40)
        for mapping in result.unmapped:
            lines.append(f"  - {mapping.violation.id}: {mapping.violation.description}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
