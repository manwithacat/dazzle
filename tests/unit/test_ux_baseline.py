"""Tests for UX contract baseline (ratchet mechanism)."""

from pathlib import Path

from dazzle.testing.ux.baseline import Baseline, compare_results


class TestBaseline:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        baseline = Baseline(
            total=10, passed=8, failed=2, contracts={"abc": "passed", "def": "failed"}
        )
        baseline.save(path)
        loaded = Baseline.load(path)
        assert loaded.total == 10
        assert loaded.contracts["abc"] == "passed"

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        loaded = Baseline.load(path)
        assert loaded.total == 0
        assert loaded.contracts == {}

    def test_compare_detects_regressions(self) -> None:
        old = Baseline(
            total=3, passed=3, failed=0, contracts={"a": "passed", "b": "passed", "c": "passed"}
        )
        new = Baseline(
            total=3, passed=2, failed=1, contracts={"a": "passed", "b": "failed", "c": "passed"}
        )
        diff = compare_results(old, new)
        assert diff.regressions == ["b"]
        assert diff.fixed == []

    def test_compare_detects_fixes(self) -> None:
        old = Baseline(total=2, passed=1, failed=1, contracts={"a": "passed", "b": "failed"})
        new = Baseline(total=2, passed=2, failed=0, contracts={"a": "passed", "b": "passed"})
        diff = compare_results(old, new)
        assert diff.regressions == []
        assert diff.fixed == ["b"]

    def test_compare_handles_new_contracts(self) -> None:
        old = Baseline(total=1, passed=1, failed=0, contracts={"a": "passed"})
        new = Baseline(total=2, passed=1, failed=1, contracts={"a": "passed", "b": "failed"})
        diff = compare_results(old, new)
        assert diff.new_failures == ["b"]
