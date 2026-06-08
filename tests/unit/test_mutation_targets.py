"""Drift guard for the mutation security-suite registry: every registered module and test
path must exist, and floors must be sane. Keeps `dazzle sentinel mutate --suite security`
from silently rotting when files move."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.testing.mutation import SECURITY_TARGETS

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_suite_is_non_empty() -> None:
    assert SECURITY_TARGETS


@pytest.mark.parametrize("target", SECURITY_TARGETS, ids=lambda t: t.module)
def test_target_paths_exist(target) -> None:
    assert (_REPO_ROOT / target.module).exists(), f"missing module {target.module}"
    for raw in target.tests:
        # strip a pytest "::node" selector before checking the file exists
        path = raw.split("::", 1)[0]
        assert (_REPO_ROOT / path).exists(), f"missing test path {path}"


@pytest.mark.parametrize("target", SECURITY_TARGETS, ids=lambda t: t.module)
def test_floor_is_sane(target) -> None:
    assert 0 <= target.floor <= 100


def test_pg_targets_use_integration_tests() -> None:
    # A needs_pg target must actually reference at least one PG enforcement test, else its
    # floor (calibrated WITH Postgres) is unreachable without a DB and the gate misleads.
    for t in SECURITY_TARGETS:
        if t.needs_pg:
            assert any("_pg.py" in path for path in t.tests), t.module


class TestSuiteExitCode:
    """A skipped target must NEVER yield a clean 0 — leaving a security module unmeasured
    has to be visible (the gate's most important property)."""

    def _outcome(self, *, passed: bool, skipped: bool = False):
        from dazzle.testing.mutation.targets import SuiteOutcome

        return SuiteOutcome(SECURITY_TARGETS[0], 0.0, 80, passed=passed, skipped=skipped)

    def test_all_pass_is_zero(self) -> None:
        from dazzle.testing.mutation.targets import GATE_OK, suite_exit_code

        assert suite_exit_code([self._outcome(passed=True)]) == GATE_OK

    def test_floor_breach_is_one(self) -> None:
        from dazzle.testing.mutation.targets import GATE_FLOOR_BREACH, suite_exit_code

        assert (
            suite_exit_code([self._outcome(passed=True), self._outcome(passed=False)])
            == GATE_FLOOR_BREACH
        )

    def test_skipped_is_two_never_zero(self) -> None:
        from dazzle.testing.mutation.targets import GATE_INCOMPLETE, suite_exit_code

        # passed=True but skipped → must NOT be a clean pass.
        assert (
            suite_exit_code([self._outcome(passed=True), self._outcome(passed=True, skipped=True)])
            == GATE_INCOMPLETE
        )

    def test_breach_outranks_skip(self) -> None:
        from dazzle.testing.mutation.targets import GATE_FLOOR_BREACH, suite_exit_code

        assert (
            suite_exit_code([self._outcome(passed=False), self._outcome(passed=True, skipped=True)])
            == GATE_FLOOR_BREACH
        )
