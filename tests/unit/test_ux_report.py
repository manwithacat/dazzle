# tests/unit/test_ux_report.py
"""Tests for UX verification report generation."""

from dazzle.testing.ux.inventory import Interaction, InteractionClass
from dazzle.testing.ux.report import generate_report
from dazzle.testing.ux.structural import StructuralResult


class TestUXReport:
    def test_empty_report(self) -> None:
        report = generate_report([], [])
        assert "0 tested" in report.summary
        assert report.coverage == 0.0

    def test_all_passing(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
            Interaction(
                cls=InteractionClass.DETAIL_VIEW,
                entity="Task",
                persona="admin",
                description="View task",
                status="passed",
            ),
        ]
        report = generate_report(interactions, [])
        assert report.coverage == 100.0
        assert report.passed == 2
        assert report.failed == 0

    def test_with_failures(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
            Interaction(
                cls=InteractionClass.CREATE_SUBMIT,
                entity="Task",
                persona="admin",
                description="Create task",
                status="failed",
                error="Form submit returned 422",
            ),
        ]
        report = generate_report(interactions, [])
        assert report.coverage == 50.0
        assert report.failed == 1

    def test_markdown_output(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
        ]
        structural = [
            StructuralResult(check_name="test_check", passed=True),
        ]
        report = generate_report(interactions, structural)
        md = report.to_markdown()
        assert "UX Verification Report" in md
        assert "100.0%" in md

    def test_json_output(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
        ]
        report = generate_report(interactions, [])
        data = report.to_json()
        assert "coverage" in data
        assert data["coverage"] == 100.0
