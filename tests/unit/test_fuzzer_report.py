"""Tests for fuzzer report generation."""

from dazzle.testing.fuzzer.oracle import Classification, FuzzResult
from dazzle.testing.fuzzer.report import generate_report


class TestReport:
    def test_empty_results_produce_valid_report(self) -> None:
        report = generate_report([])
        assert "# DSL Parser Fuzz Report" in report
        assert "0 samples" in report

    def test_report_includes_summary_counts(self) -> None:
        results = [
            FuzzResult(dsl_input="a", classification=Classification.VALID),
            FuzzResult(
                dsl_input="b", classification=Classification.CLEAN_ERROR, error_message="err"
            ),
            FuzzResult(dsl_input="c", classification=Classification.HANG, error_message="timeout"),
        ]
        report = generate_report(results)
        assert "1" in report  # at least the counts appear
        assert "HANG" in report or "hang" in report.lower()

    def test_report_lists_bugs(self) -> None:
        results = [
            FuzzResult(
                dsl_input="bad input",
                classification=Classification.CRASH,
                error_message="TypeError: ...",
                error_type="TypeError",
            ),
        ]
        report = generate_report(results)
        assert "CRASH" in report or "crash" in report.lower()
        assert "TypeError" in report

    def test_report_shows_construct_coverage(self) -> None:
        results = [
            FuzzResult(
                dsl_input="a",
                classification=Classification.VALID,
                constructs_hit=["entities", "surfaces"],
            ),
            FuzzResult(
                dsl_input="b",
                classification=Classification.VALID,
                constructs_hit=["processes"],
            ),
        ]
        report = generate_report(results)
        assert "entities" in report
        assert "surfaces" in report
        assert "processes" in report
