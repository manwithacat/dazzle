"""pytest plugin for DSL conformance testing.

Registers the ``conformance`` marker. When dazzle.toml is found in
the project root, provides ``collect_conformance_cases()`` for
test generators and ``build_conformance_report()`` for coverage metrics.

Role 1: Derivation — ``collect_conformance_cases()`` parses DSL and
derives cases + fixtures.

Role 2: Execution — ``run_conformance_session()`` boots the app, seeds
data, runs HTTP assertions, and returns pass/fail results.

Usage:
    pytest -m conformance          # run only conformance tests
    pytest -m "not conformance"    # exclude conformance tests
"""

import logging
from pathlib import Path
from typing import Any

from .derivation import derive_conformance_cases
from .fixtures import generate_fixtures
from .models import ConformanceCase, ConformanceFixtures

logger = logging.getLogger(__name__)


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "conformance: DSL conformance tests")


def collect_conformance_cases(
    project_root: Path,
    auth_enabled: bool = True,
) -> tuple[list[ConformanceCase], ConformanceFixtures]:
    """Parse DSL from project root and derive conformance cases + fixtures.

    Uses the canonical four-step pipeline: manifest → discover → parse → build.
    Requires a ``dazzle.toml`` in ``project_root``.

    Args:
        project_root: Path to the project directory containing ``dazzle.toml``.
        auth_enabled: When True, includes unauthenticated (401) cases.

    Returns:
        Tuple of (cases, fixtures) where cases have resolved expected_rows
        (sentinels replaced with concrete counts by the fixture engine).

    Raises:
        FileNotFoundError: If ``dazzle.toml`` is not found in project_root.
    """
    from dazzle.core.appspec_loader import load_project_appspec

    toml_path = project_root / "dazzle.toml"
    if not toml_path.exists():
        raise FileNotFoundError(f"No dazzle.toml found in {project_root}")

    appspec = load_project_appspec(project_root)
    cases = derive_conformance_cases(appspec, auth_enabled=auth_enabled)
    fixtures = generate_fixtures(appspec, cases)

    return cases, fixtures


def build_conformance_report(cases: list[ConformanceCase]) -> dict[str, Any]:
    """Compute conformance coverage metrics from a case list.

    Args:
        cases: ConformanceCase objects from ``collect_conformance_cases()``
               or ``derive_conformance_cases()``.

    Returns:
        A dict with:
            total_cases: int
            entities: dict mapping entity name → case count
            scope_types: dict mapping ScopeOutcome value string → count
    """
    entities: dict[str, int] = {}
    scope_types: dict[str, int] = {}

    for case in cases:
        entities[case.entity] = entities.get(case.entity, 0) + 1
        st = case.scope_type.value if hasattr(case.scope_type, "value") else str(case.scope_type)
        scope_types[st] = scope_types.get(st, 0) + 1

    return {
        "total_cases": len(cases),
        "entities": entities,
        "scope_types": scope_types,
    }


async def run_conformance_session(
    project_root: Path,
    database_url: str | None = None,
    auth_enabled: bool = True,
) -> dict[str, Any]:
    """Run a complete conformance test session (Role 2).

    Derives cases, boots the app, seeds fixtures, runs all HTTP assertions,
    and returns a structured report.

    Args:
        project_root: Path to the project directory containing ``dazzle.toml``.
        database_url: PostgreSQL URL for the test database. Falls back to
            ``CONFORMANCE_DATABASE_URL`` env var.
        auth_enabled: When True, includes unauthenticated (401) cases.

    Returns:
        A dict with:
            total: int — total cases executed
            passed: int — cases that passed
            failed: int — cases that failed
            pass_rate: float — passed / total
            failures: list of dicts describing each failed case
    """
    from .executor import ConformanceExecutor

    cases, fixtures = collect_conformance_cases(project_root, auth_enabled=auth_enabled)
    executor = ConformanceExecutor(
        project_root=project_root,
        cases=cases,
        fixtures=fixtures,
        database_url=database_url,
    )

    await executor.setup()
    try:
        results = await executor.run_all()
    finally:
        await executor.teardown()

    # Build report
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    failures = [
        {
            "test_id": r.case.test_id,
            "entity": r.case.entity,
            "persona": r.case.persona,
            "operation": r.case.operation,
            "expected_status": r.case.expected_status,
            "actual_status": r.actual_status,
            "expected_rows": r.case.expected_rows,
            "actual_rows": r.actual_rows,
            "error": r.error,
        }
        for r in results
        if not r.passed
    ]

    report = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total > 0 else 0.0,
        "failures": failures,
    }

    logger.info(
        "Conformance: %d/%d passed (%.0f%%)",
        passed,
        total,
        report["pass_rate"] * 100,  # type: ignore[operator]
    )
    if failures:
        for f in failures[:10]:
            logger.warning("  FAIL: %s — %s", f["test_id"], f["error"])

    return report
