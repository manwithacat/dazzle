"""Tests for the mutation-testing engine (graduated from the fuzz-leverage POC)."""

from __future__ import annotations

import pytest

from dazzle.testing.mutation import (
    BaselineError,
    generate_mutants,
    run_mutation,
)


class TestGenerateMutants:
    def test_swaps_comparison_operators(self) -> None:
        muts = generate_mutants("def f(a, b):\n    return a == b\n")
        afters = {m.after for _, m in muts}
        assert any("!=" in a for a in afters)

    def test_swaps_boolean_keywords(self) -> None:
        muts = generate_mutants("def f(a, b):\n    return a and b\n")
        assert any(" or " in m.after for _, m in muts)

    def test_never_mutates_strings_or_comments(self) -> None:
        # The only operators here live inside a string and a comment — none are real code.
        muts = generate_mutants('x = "a == b and c"  # a + b or c\n')
        assert muts == []

    def test_never_mutates_docstrings(self) -> None:
        muts = generate_mutants('"""a + b == c or d"""\nx = 1\n')
        assert muts == []

    def test_each_mutant_is_single_site(self) -> None:
        # `a == b` and `c < d` are two independent swap sites.
        muts = generate_mutants("def f(a, b, c, d):\n    return a == b or c < d\n")
        # at least one mutant per swappable token (==, or, <)
        assert len(muts) >= 3


def _write_module(tmp_path, body: str):
    mod = tmp_path / "m.py"
    mod.write_text(body, encoding="utf-8")
    test = tmp_path / "test_m.py"
    return mod, test


class TestRunMutation:
    def test_pinned_operator_is_killed(self, tmp_path) -> None:
        mod, test = _write_module(tmp_path, "def add(a, b):\n    return a + b\n")
        test.write_text(
            f"import sys; sys.path.insert(0, {str(tmp_path)!r})\n"
            "from m import add\n"
            "def test_add():\n    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )
        res = run_mutation(mod, [str(test)])
        assert res.total >= 1
        assert res.killed >= 1  # +→- makes add(2,3)==-1 ≠ 5 → caught

    def test_unpinned_operator_survives(self, tmp_path) -> None:
        mod, test = _write_module(tmp_path, "def add(a, b):\n    return a + b\n")
        # add(0, 0) == 0 holds for both + and - → the mutant is not caught.
        test.write_text(
            f"import sys; sys.path.insert(0, {str(tmp_path)!r})\n"
            "from m import add\n"
            "def test_add():\n    assert add(0, 0) == 0\n",
            encoding="utf-8",
        )
        res = run_mutation(mod, [str(test)])
        assert res.killed == 0
        assert any(m.after.endswith("a - b") for m in res.survivors)

    def test_baseline_failure_aborts(self, tmp_path) -> None:
        mod, test = _write_module(tmp_path, "def add(a, b):\n    return a + b\n")
        test.write_text(
            f"import sys; sys.path.insert(0, {str(tmp_path)!r})\n"
            "from m import add\n"
            "def test_add():\n    assert add(2, 3) == 999\n",  # wrong → baseline red
            encoding="utf-8",
        )
        with pytest.raises(BaselineError):
            run_mutation(mod, [str(test)])

    def test_source_is_restored_after_run(self, tmp_path) -> None:
        mod, test = _write_module(tmp_path, "def add(a, b):\n    return a + b\n")
        original = mod.read_text(encoding="utf-8")
        test.write_text(
            f"import sys; sys.path.insert(0, {str(tmp_path)!r})\n"
            "from m import add\n"
            "def test_add():\n    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )
        run_mutation(mod, [str(test)])
        assert mod.read_text(encoding="utf-8") == original

    def test_empty_tests_rejected(self, tmp_path) -> None:
        mod, _ = _write_module(tmp_path, "x = 1\n")
        with pytest.raises(ValueError):
            run_mutation(mod, [])
