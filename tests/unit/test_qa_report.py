"""Tests for dazzle.qa.report — aggregation, dedup, severity sort, formatting."""

from dazzle.qa.models import Finding, QAReport
from dazzle.qa.report import deduplicate, format_table, sort_by_severity


def _finding(
    category: str, location: str, severity: str = "low", description: str = "desc"
) -> Finding:
    return Finding(
        category=category,
        severity=severity,
        location=location,
        description=description,
        suggestion="fix it",
    )


# ---------------------------------------------------------------------------
# deduplicate
# ---------------------------------------------------------------------------


def test_deduplicate_same_category_and_location_keeps_one() -> None:
    f1 = _finding("layout", "header", description="first")
    f2 = _finding("layout", "header", description="second")
    result = deduplicate([f1, f2])
    assert len(result) == 1
    assert result[0].description == "first"


def test_deduplicate_different_locations_keeps_both() -> None:
    f1 = _finding("layout", "header")
    f2 = _finding("layout", "footer")
    result = deduplicate([f1, f2])
    assert len(result) == 2


def test_deduplicate_different_categories_keeps_both() -> None:
    f1 = _finding("layout", "header")
    f2 = _finding("colour", "header")
    result = deduplicate([f1, f2])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# sort_by_severity
# ---------------------------------------------------------------------------


def test_sort_by_severity_orders_high_medium_low() -> None:
    findings = [
        _finding("a", "x", severity="low"),
        _finding("b", "y", severity="high"),
        _finding("c", "z", severity="medium"),
    ]
    result = sort_by_severity(findings)
    assert [f.severity for f in result] == ["high", "medium", "low"]


# ---------------------------------------------------------------------------
# format_table
# ---------------------------------------------------------------------------


def test_format_table_empty_findings_says_zero_findings() -> None:
    report = QAReport(app="MyApp", findings=[])
    output = format_table(report)
    assert "0 findings" in output
    assert "No findings" in output


def test_format_table_with_findings_includes_category_and_severity() -> None:
    findings = [
        _finding("layout", "header", severity="high", description="Misaligned logo"),
        _finding("colour", "footer", severity="low", description="Low contrast"),
    ]
    report = QAReport(app="MyApp", findings=findings)
    output = format_table(report)
    assert "MyApp" in output
    assert "layout" in output
    assert "colour" in output
    assert "high" in output
    assert "low" in output
    assert "2 findings" in output
