"""pytest plugin for DSL conformance testing.

Registers the ``conformance`` marker. When dazzle.toml is found in
the project root, provides ``collect_conformance_cases()`` for
test generators and ``build_conformance_report()`` for coverage metrics.

Usage:
    pytest -m conformance          # run only conformance tests
    pytest -m "not conformance"    # exclude conformance tests
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .derivation import derive_conformance_cases
from .fixtures import generate_fixtures
from .models import ConformanceCase, ConformanceFixtures


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
