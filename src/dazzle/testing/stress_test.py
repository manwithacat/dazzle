"""
Stress Testing Framework for Dazzle Generation Pipeline.

This module provides tools for systematically finding bugs and gaps in:
1. DSL → AppSpec parsing
2. AppSpec → TestSpec generation
3. TestSpec → Playwright codegen
4. Runtime behavior vs generated test expectations

The approach:
- Cross-reference validation: Verify generated artifacts match source
- Contract testing: Assert semantic invariants hold
- Element probing: Check UI elements before test execution
- DSL mutation: Generate edge case DSL patterns

Usage:
    from dazzle.testing.stress_test import StressTestRunner

    runner = StressTestRunner(project_path)
    report = runner.run_full_analysis()
    print(report.summary())
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.testing.stress")


class GapCategory(str, Enum):
    """Categories of generation gaps."""

    MISSING_FIELD = "missing_field"  # Field in testspec doesn't exist in form
    WRONG_ELEMENT_TYPE = "wrong_element_type"  # e.g., select vs input
    MISSING_SURFACE = "missing_surface"  # Referenced surface doesn't exist
    INVALID_SELECTOR = "invalid_selector"  # Selector can't find element
    SEMANTIC_MISMATCH = "semantic_mismatch"  # Generated step doesn't match reality
    RUNTIME_ERROR = "runtime_error"  # Step causes runtime exception
    NAVIGATION_ERROR = "navigation_error"  # URL returns non-200


@dataclass
class Gap:
    """A detected generation gap."""

    category: GapCategory
    location: str  # e.g., "User_create_valid.step[3]"
    description: str
    expected: str | None = None
    actual: str | None = None
    severity: str = "medium"  # low, medium, high, critical
    suggestion: str | None = None


@dataclass
class StressTestReport:
    """Results from stress testing."""

    project_name: str
    started_at: datetime
    completed_at: datetime | None = None

    # Counts
    total_flows_analyzed: int = 0
    total_steps_analyzed: int = 0

    # Gaps by category
    gaps: list[Gap] = field(default_factory=list)

    # Coverage info
    entities_analyzed: set[str] = field(default_factory=set)
    surfaces_analyzed: set[str] = field(default_factory=set)
    field_types_seen: set[str] = field(default_factory=set)

    def add_gap(self, gap: Gap) -> None:
        """Add a detected gap."""
        self.gaps.append(gap)

    @property
    def gap_count(self) -> int:
        """Total number of gaps found."""
        return len(self.gaps)

    def gaps_by_category(self) -> dict[str, int]:
        """Count gaps by category."""
        counts: dict[str, int] = {}
        for gap in self.gaps:
            counts[gap.category.value] = counts.get(gap.category.value, 0) + 1
        return counts

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Stress Test Report: {self.project_name}",
            "=" * 50,
            f"Analyzed: {self.total_flows_analyzed} flows, {self.total_steps_analyzed} steps",
            f"Entities: {len(self.entities_analyzed)}",
            f"Surfaces: {len(self.surfaces_analyzed)}",
            f"Field types: {sorted(self.field_types_seen)}",
            "",
            f"Gaps Found: {self.gap_count}",
        ]

        if self.gaps:
            lines.append("-" * 40)
            by_cat = self.gaps_by_category()
            for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
                lines.append(f"  {cat}: {count}")

            lines.append("")
            lines.append("Details:")
            for _i, gap in enumerate(self.gaps[:20]):  # Limit to 20
                lines.append(f"  [{gap.severity.upper()}] {gap.category.value}")
                lines.append(f"    Location: {gap.location}")
                lines.append(f"    {gap.description}")
                if gap.suggestion:
                    lines.append(f"    Suggestion: {gap.suggestion}")

            if len(self.gaps) > 20:
                lines.append(f"  ... and {len(self.gaps) - 20} more gaps")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_name": self.project_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_flows_analyzed": self.total_flows_analyzed,
            "total_steps_analyzed": self.total_steps_analyzed,
            "gap_count": self.gap_count,
            "gaps_by_category": self.gaps_by_category(),
            "entities_analyzed": sorted(self.entities_analyzed),
            "surfaces_analyzed": sorted(self.surfaces_analyzed),
            "field_types_seen": sorted(self.field_types_seen),
            "gaps": [
                {
                    "category": g.category.value,
                    "location": g.location,
                    "description": g.description,
                    "expected": g.expected,
                    "actual": g.actual,
                    "severity": g.severity,
                    "suggestion": g.suggestion,
                }
                for g in self.gaps
            ],
        }


class StressTestRunner:
    """
    Runs stress tests on the generation pipeline.

    Validates:
    1. Cross-reference: TestSpec matches AppSpec
    2. Element probing: UI elements exist and match types
    3. Contract assertions: Semantic invariants hold
    """

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.appspec = None
        self.testspec = None
        self.report: StressTestReport | None = None

    def load_specs(self) -> None:
        """Load AppSpec and generate TestSpec."""
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules
        from dazzle.testing.testspec_generator import generate_e2e_testspec

        manifest_path = self.project_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(self.project_path, manifest)
        modules = parse_modules(dsl_files)
        self.appspec = build_appspec(modules, manifest.project_root)
        self.testspec = generate_e2e_testspec(self.appspec, manifest)

    def run_full_analysis(self) -> StressTestReport:
        """Run complete stress test analysis."""
        self.load_specs()

        self.report = StressTestReport(
            project_name=self.appspec.name,
            started_at=datetime.now(),
        )

        # Run each type of validation
        self._validate_cross_references()
        self._validate_field_types()
        self._validate_surfaces()
        self._validate_navigation_targets()
        self._validate_form_fields()

        self.report.completed_at = datetime.now()
        return self.report

    def _validate_cross_references(self) -> None:
        """Validate that TestSpec references match AppSpec."""
        entity_fields: dict[str, set[str]] = {}
        entity_field_types: dict[str, dict[str, str]] = {}

        # Build entity field index from AppSpec
        for entity in self.appspec.domain.entities:
            entity_fields[entity.name] = {f.name for f in entity.fields}
            entity_field_types[entity.name] = {f.name: f.type.kind.value for f in entity.fields}
            self.report.entities_analyzed.add(entity.name)

        # Check each flow's steps
        for flow in self.testspec.flows:
            self.report.total_flows_analyzed += 1

            for i, step in enumerate(flow.steps):
                self.report.total_steps_analyzed += 1
                location = f"{flow.id}.step[{i}]"

                # Check field references
                if step.target and step.target.startswith("field:"):
                    self._validate_field_reference(
                        step.target, location, entity_fields, entity_field_types
                    )

    def _validate_field_reference(
        self,
        target: str,
        location: str,
        entity_fields: dict[str, set[str]],
        entity_field_types: dict[str, dict[str, str]],
    ) -> None:
        """Validate a field reference target."""
        # Parse "field:Entity.field_name"
        field_ref = target.split(":", 1)[1]
        if "." not in field_ref:
            return

        entity_name, field_name = field_ref.split(".", 1)

        # Check entity exists
        if entity_name not in entity_fields:
            self.report.add_gap(
                Gap(
                    category=GapCategory.SEMANTIC_MISMATCH,
                    location=location,
                    description=f"Entity '{entity_name}' not found in AppSpec",
                    severity="high",
                    suggestion="Check if entity name is correct or if it's defined in DSL",
                )
            )
            return

        # Check field exists
        if field_name not in entity_fields[entity_name]:
            self.report.add_gap(
                Gap(
                    category=GapCategory.MISSING_FIELD,
                    location=location,
                    description=f"Field '{field_name}' not found in entity '{entity_name}'",
                    expected=f"Field should exist in {entity_name}",
                    actual=f"Available fields: {sorted(entity_fields[entity_name])}",
                    severity="high",
                    suggestion="Field may be computed/virtual or has a different name",
                )
            )
            return

        # Track field type
        field_type = entity_field_types[entity_name].get(field_name, "unknown")
        self.report.field_types_seen.add(field_type)

    def _validate_field_types(self) -> None:
        """Validate field type consistency."""
        for flow in self.testspec.flows:
            for i, step in enumerate(flow.steps):
                location = f"{flow.id}.step[{i}]"

                # Check fill steps have correct field_type
                if step.kind.value == "fill" and step.target:
                    field_type = getattr(step, "field_type", None)

                    if not field_type:
                        self.report.add_gap(
                            Gap(
                                category=GapCategory.SEMANTIC_MISMATCH,
                                location=location,
                                description="FILL step missing field_type",
                                expected="field_type should be set for proper element interaction",
                                severity="medium",
                                suggestion="Ensure testspec generator sets field_type for all FILL steps",
                            )
                        )

    def _validate_surfaces(self) -> None:
        """Validate surface references."""
        surface_names = {s.name for s in self.appspec.surfaces}
        self.report.surfaces_analyzed.update(surface_names)

        for flow in self.testspec.flows:
            for _i, step in enumerate(flow.steps):
                # Check view references
                if step.target and step.target.startswith("view:"):
                    view_name = step.target.split(":", 1)[1]

                    # Simple heuristic: view name should relate to a surface
                    # e.g., "task_list" should have a surface for "Task"
                    found_related = False
                    for surface_name in surface_names:
                        if (
                            surface_name.lower() in view_name.lower()
                            or view_name.lower() in surface_name.lower()
                        ):
                            found_related = True
                            break

                    if not found_related and view_name not in surface_names:
                        # This is just a warning, not necessarily a bug
                        logger.debug(f"View '{view_name}' may not have a matching surface")

    def _validate_navigation_targets(self) -> None:
        """Validate navigation targets."""
        for flow in self.testspec.flows:
            for i, step in enumerate(flow.steps):
                location = f"{flow.id}.step[{i}]"

                if step.kind.value == "navigate" and not step.target:
                    self.report.add_gap(
                        Gap(
                            category=GapCategory.NAVIGATION_ERROR,
                            location=location,
                            description="NAVIGATE step has no target",
                            severity="high",
                            suggestion="All navigate steps should have a target view or URL",
                        )
                    )

    def _validate_form_fields(self) -> None:
        """
        Validate that FILL steps target fields that exist in surface definitions.

        The key insight: CRUD flows should only fill fields that appear in the
        corresponding surface (create/edit). If the testspec fills a field not
        in the surface, it will fail at runtime.
        """
        from dazzle.core.ir import FieldModifier

        # Build index of surface fields by entity and mode
        # e.g., {"User": {"create": {"name", "email", ...}, "edit": {...}}}
        surface_fields: dict[str, dict[str, set[str]]] = {}

        for surface in self.appspec.surfaces:
            if not surface.entity_ref or not surface.mode:
                continue

            entity_name = surface.entity_ref
            mode = surface.mode.value

            if entity_name not in surface_fields:
                surface_fields[entity_name] = {}

            # Collect field names from surface sections
            field_names: set[str] = set()
            for section in surface.sections:
                for element in section.elements:
                    # field_name can be "Entity.field_name" or just "field_name"
                    if "." in element.field_name:
                        field_names.add(element.field_name.split(".", 1)[1])
                    else:
                        field_names.add(element.field_name)

            surface_fields[entity_name][mode] = field_names

        # Build index of field properties
        field_info: dict[str, dict[str, Any]] = {}
        for entity in self.appspec.domain.entities:
            for field_spec in entity.fields:
                key = f"{entity.name}.{field_spec.name}"
                is_required = FieldModifier.REQUIRED in field_spec.modifiers
                is_optional = FieldModifier.OPTIONAL in field_spec.modifiers
                # Fields without explicit modifier are implicitly optional
                is_implicitly_optional = not is_required and not is_optional

                field_info[key] = {
                    "required": is_required,
                    "optional": is_optional or is_implicitly_optional,
                    "has_default": field_spec.default is not None,
                    "is_pk": field_spec.is_primary_key,
                    "is_auto": (
                        FieldModifier.AUTO_ADD in field_spec.modifiers
                        or FieldModifier.AUTO_UPDATE in field_spec.modifiers
                    ),
                    "type": field_spec.type.kind.value,
                    "name": field_spec.name,
                }

        # Check each CRUD flow
        for flow in self.testspec.flows:
            # Determine flow type and entity
            entity_name = flow.entity
            if not entity_name:
                continue

            # Determine mode from flow ID
            mode: str | None = None
            if "_create_" in flow.id or flow.id.endswith("_create_valid"):
                mode = "create"
            elif "_update_" in flow.id or "_edit_" in flow.id:
                mode = "edit"

            if not mode:
                continue

            # Get fields defined in the surface for this entity/mode
            surface_field_set = surface_fields.get(entity_name, {}).get(mode, set())

            for i, step in enumerate(flow.steps):
                if step.kind.value != "fill" or not step.target:
                    continue

                location = f"{flow.id}.step[{i}]"

                # Parse field reference
                if not step.target.startswith("field:"):
                    continue

                field_ref = step.target.split(":", 1)[1]
                if "." not in field_ref:
                    continue

                step_entity, step_field = field_ref.split(".", 1)

                # Check if this entity/mode has surface definition
                if step_entity == entity_name and surface_field_set:
                    if step_field not in surface_field_set:
                        info = field_info.get(field_ref, {})
                        self.report.add_gap(
                            Gap(
                                category=GapCategory.MISSING_FIELD,
                                location=location,
                                description=(
                                    f"Field '{step_field}' is not defined in the {mode} "
                                    f"surface for {entity_name}. Test will fail with 'element not found'."
                                ),
                                expected=f"Field should be in surface_{entity_name.lower()}_{mode}",
                                actual=f"Surface fields: {sorted(surface_field_set)}",
                                severity="high",
                                suggestion=(
                                    "Either: (1) Add field to surface definition, or "
                                    "(2) Exclude field from testspec generation"
                                ),
                            )
                        )

                # Also flag auto-generated fields
                info = field_info.get(field_ref)
                if info and info["is_auto"]:
                    self.report.add_gap(
                        Gap(
                            category=GapCategory.SEMANTIC_MISMATCH,
                            location=location,
                            description=f"Field '{info['name']}' is auto-generated but testspec tries to fill it",
                            severity="high",
                            suggestion="Remove FILL step for auto-generated fields",
                        )
                    )


class ElementProber:
    """
    Probes the running UI to detect element mismatches.

    Requires a running server and Playwright.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url

    def probe_form_fields(
        self,
        page: Any,
        entity_name: str,
    ) -> dict[str, dict[str, Any]]:
        """
        Probe all form fields for an entity.

        Returns:
            Dict mapping field_name to {element_type, selector, visible, ...}
        """
        results: dict[str, dict[str, Any]] = {}

        # Find all fields for this entity
        selector = f"[data-dazzle-field^='{entity_name}.']"
        elements = page.locator(selector).all()

        for element in elements:
            field_attr = element.get_attribute("data-dazzle-field")
            if not field_attr:
                continue

            field_name = field_attr.split(".", 1)[1] if "." in field_attr else field_attr

            results[field_name] = {
                "selector": f"[data-dazzle-field='{field_attr}']",
                "tag_name": element.evaluate("el => el.tagName.toLowerCase()"),
                "element_type": element.get_attribute("type") or "text",
                "field_type_attr": element.get_attribute("data-dazzle-field-type"),
                "visible": element.is_visible(),
                "enabled": element.is_enabled(),
            }

        return results

    def validate_step_element(
        self,
        page: Any,
        step: Any,
    ) -> Gap | None:
        """
        Validate that a step's target element exists and matches expectations.

        Returns:
            Gap if mismatch found, None if valid
        """
        if not step.target or not step.target.startswith("field:"):
            return None

        field_ref = step.target.split(":", 1)[1]
        selector = f"[data-dazzle-field='{field_ref}']"

        locator = page.locator(selector)

        # Check element exists
        if locator.count() == 0:
            return Gap(
                category=GapCategory.INVALID_SELECTOR,
                location=f"step.target={step.target}",
                description=f"No element found for selector: {selector}",
                severity="high",
                suggestion="Element may be hidden, in a different view, or have a different selector",
            )

        # Check element type matches field_type
        element = locator.first
        tag_name = element.evaluate("el => el.tagName.toLowerCase()")
        field_type = getattr(step, "field_type", None)

        if field_type in ("enum", "ref") and tag_name != "select":
            return Gap(
                category=GapCategory.WRONG_ELEMENT_TYPE,
                location=f"step.target={step.target}",
                description=f"Expected <select> for {field_type} field, found <{tag_name}>",
                expected="select",
                actual=tag_name,
                severity="high",
                suggestion="UI may render this as a different component (radio, dropdown, etc.)",
            )

        if field_type == "bool" and tag_name != "input":
            actual_type = element.get_attribute("type")
            if actual_type != "checkbox":
                return Gap(
                    category=GapCategory.WRONG_ELEMENT_TYPE,
                    location=f"step.target={step.target}",
                    description=f"Expected checkbox for bool field, found <{tag_name} type='{actual_type}'>",
                    expected="input[type=checkbox]",
                    actual=f"{tag_name}[type={actual_type}]",
                    severity="high",
                )

        return None


def run_stress_test(project_path: Path) -> StressTestReport:
    """
    Convenience function to run stress tests.

    Args:
        project_path: Path to Dazzle project

    Returns:
        StressTestReport with all findings
    """
    runner = StressTestRunner(project_path)
    return runner.run_full_analysis()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m dazzle.testing.stress_test <project_path>")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    report = run_stress_test(project_path)
    print(report.summary())
    print()
    print("JSON output:")
    print(json.dumps(report.to_dict(), indent=2))
