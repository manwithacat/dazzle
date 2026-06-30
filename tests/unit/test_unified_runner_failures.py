"""UnifiedTestResult._failure_details includes error-status tests (#1513).

An ``error`` status carries the exception text in ``error_message``; the old
filter dropped everything but ``failed``, hiding the actual reason a test
errored. Each entry now also carries a ``status`` key so a consumer can tell an
assertion failure from a harness error.
"""

from datetime import datetime

# Aliased on import — the source names are ``Test``-prefixed dataclasses, which
# pytest would otherwise try to collect as test classes (emitting warnings).
from dazzle.testing.test_runner import TestCaseResult as CaseResult
from dazzle.testing.test_runner import TestResult as Status
from dazzle.testing.test_runner import TestRunResult as RunResult
from dazzle.testing.unified_runner import UnifiedTestResult


def _result(*cases: CaseResult) -> RunResult:
    return RunResult(
        project_name="demo",
        started_at=datetime(2026, 6, 30),
        tests=list(cases),
    )


def _case(test_id: str, result: Status, error: str = "") -> CaseResult:
    return CaseResult(test_id=test_id, title=test_id, result=result, error_message=error)


def test_error_status_tests_are_included_with_their_message() -> None:
    crud = _result(
        _case("AUTH_LOGIN_VALID", Status.ERROR, "NameError: name 'Path' is not defined"),
        _case("ACL_READ", Status.PASSED),
        _case("GOAL_CREATE", Status.FAILED, "expected 201, got 403"),
    )
    unified = UnifiedTestResult(
        project_name="demo", started_at=datetime(2026, 6, 30), crud_result=crud
    )

    failures = unified._failure_details()
    by_id = {f["id"]: f for f in failures}

    assert set(by_id) == {"AUTH_LOGIN_VALID", "GOAL_CREATE"}  # passed excluded
    assert by_id["AUTH_LOGIN_VALID"]["status"] == "error"
    assert "NameError" in by_id["AUTH_LOGIN_VALID"]["error"]
    assert by_id["GOAL_CREATE"]["status"] == "failed"


def test_limit_is_respected_across_statuses() -> None:
    crud = _result(*[_case(f"E{i}", Status.ERROR, "boom") for i in range(5)])
    unified = UnifiedTestResult(
        project_name="demo", started_at=datetime(2026, 6, 30), crud_result=crud
    )
    assert len(unified._failure_details(limit=3)) == 3
