"""Tests for dazzle.qa models and evaluation categories."""

from pathlib import Path

from dazzle.qa import CapturedScreen, Finding, QAReport
from dazzle.qa.categories import CATEGORIES, get_category


class TestCapturedScreen:
    def test_required_fields(self) -> None:
        screen = CapturedScreen(
            persona="teacher",
            workspace="teacher_workspace",
            url="/app/workspaces/teacher_workspace",
            screenshot=Path(".dazzle/qa/screenshots/teacher_workspace_teacher.png"),
        )
        assert screen.persona == "teacher"
        assert screen.workspace == "teacher_workspace"
        assert screen.url == "/app/workspaces/teacher_workspace"
        assert screen.screenshot == Path(".dazzle/qa/screenshots/teacher_workspace_teacher.png")

    def test_default_viewport(self) -> None:
        screen = CapturedScreen(
            persona="admin",
            workspace="admin_workspace",
            url="/app/workspaces/admin_workspace",
            screenshot=Path("screenshot.png"),
        )
        assert screen.viewport == "desktop"

    def test_timestamp_set_automatically(self) -> None:
        screen = CapturedScreen(
            persona="admin",
            workspace="admin_workspace",
            url="/app/workspaces/admin_workspace",
            screenshot=Path("screenshot.png"),
        )
        assert screen.timestamp is not None

    def test_custom_viewport(self) -> None:
        screen = CapturedScreen(
            persona="admin",
            workspace="admin_workspace",
            url="/app/workspaces/admin_workspace",
            screenshot=Path("screenshot.png"),
            viewport="mobile",
        )
        assert screen.viewport == "mobile"


class TestFinding:
    def test_required_fields(self) -> None:
        finding = Finding(
            category="data_quality",
            severity="high",
            location="teacher_workspace > Student column",
            description="UUID visible instead of student name",
            suggestion="Apply ref_display filter",
        )
        assert finding.category == "data_quality"
        assert finding.severity == "high"
        assert finding.location == "teacher_workspace > Student column"
        assert finding.description == "UUID visible instead of student name"
        assert finding.suggestion == "Apply ref_display filter"


class TestQAReport:
    def test_empty_report(self) -> None:
        report = QAReport(app="my_app")
        assert report.app == "my_app"
        assert report.findings == []
        assert report.total == 0
        assert report.high_count == 0
        assert report.medium_count == 0
        assert report.low_count == 0

    def test_report_with_findings(self) -> None:
        findings = [
            Finding(
                category="data_quality",
                severity="high",
                location="workspace > col",
                description="UUID visible",
                suggestion="Fix it",
            ),
            Finding(
                category="alignment",
                severity="low",
                location="workspace > header",
                description="Misaligned",
                suggestion="Fix spacing",
            ),
            Finding(
                category="truncation",
                severity="medium",
                location="workspace > name col",
                description="Name cut off",
                suggestion="Widen column",
            ),
            Finding(
                category="title_formatting",
                severity="high",
                location="workspace > card",
                description="Title inline with content",
                suggestion="Move title above",
            ),
        ]
        report = QAReport(app="test_app", findings=findings)
        assert report.total == 4
        assert report.high_count == 2
        assert report.medium_count == 1
        assert report.low_count == 1


class TestCategories:
    def test_eight_categories_defined(self) -> None:
        assert len(CATEGORIES) == 8

    def test_category_ids_match_expected_set(self) -> None:
        expected_ids = {
            "text_wrapping",
            "truncation",
            "title_formatting",
            "column_layout",
            "empty_state",
            "alignment",
            "readability",
            "data_quality",
        }
        actual_ids = {c.id for c in CATEGORIES}
        assert actual_ids == expected_ids

    def test_each_category_has_required_fields(self) -> None:
        for cat in CATEGORIES:
            assert cat.id, f"Category missing id: {cat}"
            assert cat.definition, f"Category {cat.id} missing definition"
            assert cat.example, f"Category {cat.id} missing example"
            assert cat.severity_default in (
                "high",
                "medium",
                "low",
            ), f"Category {cat.id} has invalid severity_default: {cat.severity_default}"

    def test_get_category_by_id(self) -> None:
        cat = get_category("data_quality")
        assert cat is not None
        assert cat.id == "data_quality"
        assert cat.severity_default == "high"

    def test_get_category_unknown_returns_none(self) -> None:
        result = get_category("nonexistent_category")
        assert result is None

    def test_high_severity_categories(self) -> None:
        high_cats = {c.id for c in CATEGORIES if c.severity_default == "high"}
        assert "title_formatting" in high_cats
        assert "data_quality" in high_cats

    def test_medium_severity_categories(self) -> None:
        medium_cats = {c.id for c in CATEGORIES if c.severity_default == "medium"}
        assert "text_wrapping" in medium_cats
        assert "truncation" in medium_cats
        assert "column_layout" in medium_cats
        assert "readability" in medium_cats

    def test_low_severity_categories(self) -> None:
        low_cats = {c.id for c in CATEGORIES if c.severity_default == "low"}
        assert "empty_state" in low_cats
        assert "alignment" in low_cats
