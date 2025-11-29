"""Unit tests for WCAG violation mapping module."""

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    SurfaceMode,
    SurfaceSpec,
    WorkspaceSpec,
)
from dazzle_e2e.accessibility import AxeNode, AxeViolation
from dazzle_e2e.wcag_mapping import (
    AXE_TO_WCAG,
    WCAG_CRITERIA,
    WCAGMapper,
    WCAGMappingResult,
    WCAGViolationMapping,
    format_violation_report,
    map_violations_to_appspec,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def make_appspec() -> AppSpec:
    """Create a test AppSpec."""
    return AppSpec(
        name="test_app",
        title="Test App",
        version="1.0.0",
        domain=DomainSpec(
            entities=[
                EntitySpec(
                    name="Task",
                    display_name="Task",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind=FieldTypeKind.UUID),
                            modifiers=[FieldModifier.PK],
                        ),
                        FieldSpec(
                            name="title",
                            type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                            modifiers=[FieldModifier.REQUIRED],
                        ),
                    ],
                ),
                EntitySpec(
                    name="User",
                    display_name="User",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind=FieldTypeKind.UUID),
                            modifiers=[FieldModifier.PK],
                        ),
                        FieldSpec(
                            name="email",
                            type=FieldType(kind=FieldTypeKind.EMAIL),
                            modifiers=[FieldModifier.REQUIRED],
                        ),
                    ],
                ),
            ]
        ),
        surfaces=[
            SurfaceSpec(
                name="task_list",
                display_name="Task List",
                entity_name="Task",
                mode=SurfaceMode.LIST,
            ),
            SurfaceSpec(
                name="task_detail",
                display_name="Task Detail",
                entity_name="Task",
                mode=SurfaceMode.VIEW,
            ),
        ],
        workspaces=[
            WorkspaceSpec(
                name="dashboard",
                display_name="Dashboard",
            ),
        ],
    )


def make_violation(
    rule_id: str = "color-contrast",
    impact: str = "serious",
    tags: list[str] | None = None,
    nodes: list[AxeNode] | None = None,
) -> AxeViolation:
    """Create a test violation."""
    return AxeViolation(
        id=rule_id,
        impact=impact,
        description=f"Test violation for {rule_id}",
        help=f"Fix the {rule_id} issue",
        help_url=f"https://example.com/{rule_id}",
        tags=tags or ["wcag2aa"],
        nodes=nodes or [],
    )


# =============================================================================
# WCAG Criteria Tests
# =============================================================================


class TestWCAGCriteria:
    """Tests for WCAG criteria definitions."""

    def test_level_a_criteria_exist(self):
        """Level A criteria should be defined."""
        level_a = [c for c, info in WCAG_CRITERIA.items() if info["level"] == "A"]
        assert len(level_a) >= 10
        assert "1.1.1" in [c for c, info in WCAG_CRITERIA.items()]
        assert "2.4.4" in [c for c, info in WCAG_CRITERIA.items()]

    def test_level_aa_criteria_exist(self):
        """Level AA criteria should be defined."""
        level_aa = [c for c, info in WCAG_CRITERIA.items() if info["level"] == "AA"]
        assert len(level_aa) >= 10
        assert "1.4.3" in [c for c, info in WCAG_CRITERIA.items()]

    def test_criteria_have_required_fields(self):
        """Each criterion should have required fields."""
        for criterion, info in WCAG_CRITERIA.items():
            assert "name" in info, f"{criterion} missing name"
            assert "level" in info, f"{criterion} missing level"
            assert "description" in info, f"{criterion} missing description"


class TestAxeToWCAGMapping:
    """Tests for axe rule to WCAG mapping."""

    def test_common_rules_mapped(self):
        """Common axe rules should be mapped to WCAG."""
        assert "color-contrast" in AXE_TO_WCAG
        assert "label" in AXE_TO_WCAG
        assert "button-name" in AXE_TO_WCAG
        assert "link-name" in AXE_TO_WCAG
        assert "image-alt" in AXE_TO_WCAG

    def test_color_contrast_mapping(self):
        """color-contrast should map to 1.4.3."""
        assert "1.4.3" in AXE_TO_WCAG["color-contrast"]

    def test_label_mapping(self):
        """label should map to 1.3.1 and 3.3.2."""
        assert "1.3.1" in AXE_TO_WCAG["label"]
        assert "3.3.2" in AXE_TO_WCAG["label"]


# =============================================================================
# WCAGViolationMapping Tests
# =============================================================================


class TestWCAGViolationMapping:
    """Tests for WCAGViolationMapping dataclass."""

    def test_has_mapping_with_entity(self):
        """Mapping with entity is considered mapped."""
        mapping = WCAGViolationMapping(
            violation=make_violation(),
            wcag_criterion="1.4.3",
            wcag_name="Contrast",
            wcag_level="AA",
            wcag_description="Test",
            entity_name="Task",
        )

        assert mapping.has_mapping

    def test_has_mapping_with_surface(self):
        """Mapping with surface is considered mapped."""
        mapping = WCAGViolationMapping(
            violation=make_violation(),
            wcag_criterion="1.4.3",
            wcag_name="Contrast",
            wcag_level="AA",
            wcag_description="Test",
            surface_name="task_list",
        )

        assert mapping.has_mapping

    def test_no_mapping(self):
        """Mapping without AppSpec location is not mapped."""
        mapping = WCAGViolationMapping(
            violation=make_violation(),
            wcag_criterion="1.4.3",
            wcag_name="Contrast",
            wcag_level="AA",
            wcag_description="Test",
        )

        assert not mapping.has_mapping


# =============================================================================
# WCAGMapper Tests
# =============================================================================


class TestWCAGMapper:
    """Tests for WCAGMapper class."""

    def test_map_color_contrast(self):
        """Map color-contrast violation to WCAG."""
        appspec = make_appspec()
        mapper = WCAGMapper(appspec)

        violation = make_violation(
            rule_id="color-contrast",
            tags=["wcag2aa", "wcag143"],
        )

        result = mapper.map_violations([violation])

        assert len(result.mapped_violations) >= 1
        assert result.mapped_violations[0].wcag_criterion == "1.4.3"
        assert result.mapped_violations[0].wcag_level == "AA"

    def test_map_violation_with_entity_node(self):
        """Map violation with entity info in node."""
        appspec = make_appspec()
        mapper = WCAGMapper(appspec)

        node = AxeNode(
            html='<input data-dazzle-field="Task.title">',
            target=["[data-dazzle-field='Task.title']"],
            dazzle_entity="Task",
            dazzle_field="Task.title",
        )

        violation = make_violation(
            rule_id="label",
            tags=["wcag2a"],
            nodes=[node],
        )

        result = mapper.map_violations([violation])

        assert len(result.mapped_violations) >= 1
        mapping = result.mapped_violations[0]
        assert mapping.entity_name == "Task"
        assert mapping.field_name == "Task.title"
        assert mapping.has_mapping

    def test_map_violation_with_surface_node(self):
        """Map violation with surface info in node."""
        appspec = make_appspec()
        mapper = WCAGMapper(appspec)

        node = AxeNode(
            html='<div data-dazzle-view="task_list">',
            target=["[data-dazzle-view='task_list']"],
            dazzle_view="task_list",
        )

        violation = make_violation(
            rule_id="heading-order",
            tags=["wcag2a"],
            nodes=[node],
        )

        result = mapper.map_violations([violation])

        # Find the mapping that has surface
        surface_mappings = [m for m in result.mapped_violations if m.surface_name]
        assert len(surface_mappings) >= 1
        assert surface_mappings[0].surface_name == "task_list"

    def test_map_violation_with_workspace_node(self):
        """Map violation with workspace info in node."""
        appspec = make_appspec()
        mapper = WCAGMapper(appspec)

        node = AxeNode(
            html='<div data-dazzle-view="dashboard">',
            target=["[data-dazzle-view='dashboard']"],
            dazzle_view="dashboard",
        )

        violation = make_violation(
            rule_id="bypass",
            tags=["wcag2a"],
            nodes=[node],
        )

        result = mapper.map_violations([violation])

        workspace_mappings = [m for m in result.mapped_violations if m.workspace_name]
        assert len(workspace_mappings) >= 1
        assert workspace_mappings[0].workspace_name == "dashboard"

    def test_unmapped_violation(self):
        """Violation without AppSpec info should be unmapped."""
        appspec = make_appspec()
        mapper = WCAGMapper(appspec)

        violation = make_violation(
            rule_id="document-title",
            tags=["wcag2a"],
            nodes=[],
        )

        result = mapper.map_violations([violation])

        assert len(result.unmapped) >= 1

    def test_suggested_fix_for_color_contrast(self):
        """Color contrast should have specific fix suggestion."""
        appspec = make_appspec()
        mapper = WCAGMapper(appspec)

        violation = make_violation(rule_id="color-contrast")
        result = mapper.map_violations([violation])

        assert result.mapped_violations[0].suggested_fix is not None
        assert "contrast" in result.mapped_violations[0].suggested_fix.lower()

    def test_suggested_fix_for_label(self):
        """Label violation should have specific fix suggestion."""
        appspec = make_appspec()
        mapper = WCAGMapper(appspec)

        node = AxeNode(
            html="<input>",
            target=["input"],
            dazzle_field="Task.title",
        )

        violation = make_violation(
            rule_id="label",
            nodes=[node],
        )

        result = mapper.map_violations([violation])

        assert result.mapped_violations[0].suggested_fix is not None
        assert "label" in result.mapped_violations[0].suggested_fix.lower()


# =============================================================================
# WCAGMappingResult Tests
# =============================================================================


class TestWCAGMappingResult:
    """Tests for WCAGMappingResult dataclass."""

    def test_total_violations(self):
        """Count total violations."""
        result = WCAGMappingResult(
            mapped_violations=[
                WCAGViolationMapping(
                    violation=make_violation(),
                    wcag_criterion="1.4.3",
                    wcag_name="Test",
                    wcag_level="AA",
                    wcag_description="Test",
                ),
                WCAGViolationMapping(
                    violation=make_violation(),
                    wcag_criterion="2.4.4",
                    wcag_name="Test",
                    wcag_level="A",
                    wcag_description="Test",
                ),
            ]
        )

        assert result.total_violations == 2

    def test_mapped_count(self):
        """Count mapped violations."""
        result = WCAGMappingResult(
            mapped_violations=[
                WCAGViolationMapping(
                    violation=make_violation(),
                    wcag_criterion="1.4.3",
                    wcag_name="Test",
                    wcag_level="AA",
                    wcag_description="Test",
                    entity_name="Task",
                ),
                WCAGViolationMapping(
                    violation=make_violation(),
                    wcag_criterion="2.4.4",
                    wcag_name="Test",
                    wcag_level="A",
                    wcag_description="Test",
                    # No mapping
                ),
            ]
        )

        assert result.mapped_count == 1

    def test_by_entity_indexing(self):
        """Violations indexed by entity."""
        mapping = WCAGViolationMapping(
            violation=make_violation(),
            wcag_criterion="1.4.3",
            wcag_name="Test",
            wcag_level="AA",
            wcag_description="Test",
            entity_name="Task",
        )

        result = WCAGMappingResult(
            mapped_violations=[mapping],
            by_entity={"Task": [mapping]},
        )

        assert "Task" in result.by_entity
        assert len(result.by_entity["Task"]) == 1

    def test_by_criterion_indexing(self):
        """Violations indexed by WCAG criterion."""
        mapping = WCAGViolationMapping(
            violation=make_violation(),
            wcag_criterion="1.4.3",
            wcag_name="Test",
            wcag_level="AA",
            wcag_description="Test",
        )

        result = WCAGMappingResult(
            mapped_violations=[mapping],
            by_criterion={"1.4.3": [mapping]},
        )

        assert "1.4.3" in result.by_criterion


# =============================================================================
# Integration Tests
# =============================================================================


class TestMapViolationsToAppspec:
    """Integration tests for map_violations_to_appspec function."""

    def test_map_multiple_violations(self):
        """Map multiple violations to AppSpec."""
        appspec = make_appspec()

        violations = [
            make_violation(
                rule_id="color-contrast",
                nodes=[
                    AxeNode(
                        html="<span>",
                        target=["span"],
                        dazzle_entity="Task",
                    )
                ],
            ),
            make_violation(
                rule_id="label",
                nodes=[
                    AxeNode(
                        html="<input>",
                        target=["input"],
                        dazzle_field="User.email",
                        dazzle_entity="User",
                    )
                ],
            ),
        ]

        result = map_violations_to_appspec(violations, appspec)

        assert result.total_violations >= 2
        assert "Task" in result.by_entity or "User" in result.by_entity


class TestFormatViolationReport:
    """Tests for format_violation_report function."""

    def test_report_format(self):
        """Report should be formatted correctly."""
        mapping = WCAGViolationMapping(
            violation=make_violation(),
            wcag_criterion="1.4.3",
            wcag_name="Contrast (Minimum)",
            wcag_level="AA",
            wcag_description="Test",
            entity_name="Task",
            suggested_fix="Increase contrast",
        )

        result = WCAGMappingResult(
            mapped_violations=[mapping],
            by_entity={"Task": [mapping]},
            by_criterion={"1.4.3": [mapping]},
        )

        report = format_violation_report(result)

        assert "WCAG Accessibility Violation Report" in report
        assert "Total violations: 1" in report
        assert "1.4.3" in report
        assert "Task" in report

    def test_empty_report(self):
        """Report handles empty results."""
        result = WCAGMappingResult()
        report = format_violation_report(result)

        assert "Total violations: 0" in report
