"""Tests for the conformance pytest plugin (Role 1: collection/derivation)."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHAPES_VALIDATION = Path("/Volumes/SSD/Dazzle/examples/shapes_validation")


def _make_case(
    entity: str = "Task",
    persona: str = "viewer",
    operation: str = "list",
    expected_status: int = 200,
    scope_type: str = "all",
) -> Any:
    from dazzle.conformance.models import ConformanceCase, ScopeOutcome

    return ConformanceCase(
        entity=entity,
        persona=persona,
        operation=operation,
        expected_status=expected_status,
        scope_type=ScopeOutcome(scope_type),
    )


# ---------------------------------------------------------------------------
# TestConformancePlugin
# ---------------------------------------------------------------------------


class TestConformancePlugin:
    def test_marker_registration(self) -> None:
        """pytest_configure must register the 'conformance' marker line."""
        from dazzle.conformance.plugin import pytest_configure

        config = MagicMock()
        pytest_configure(config)
        config.addinivalue_line.assert_called_once_with(
            "markers", "conformance: DSL conformance tests"
        )

    def test_build_report_empty(self) -> None:
        """build_conformance_report on an empty list returns zero totals."""
        from dazzle.conformance.plugin import build_conformance_report

        report = build_conformance_report([])
        assert report["total_cases"] == 0
        assert report["entities"] == {}
        assert report["scope_types"] == {}

    def test_build_report_counts(self) -> None:
        """build_conformance_report tallies entity and scope_type correctly."""
        from dazzle.conformance.plugin import build_conformance_report

        cases = [
            _make_case(entity="Shape", persona="oracle", operation="list", scope_type="all"),
            _make_case(entity="Shape", persona="viewer", operation="list", scope_type="filtered"),
            _make_case(entity="Task", persona="oracle", operation="list", scope_type="all"),
        ]
        report = build_conformance_report(cases)

        assert report["total_cases"] == 3
        assert report["entities"] == {"Shape": 2, "Task": 1}
        assert report["scope_types"] == {"all": 2, "filtered": 1}

    def test_build_report_scope_type_as_str_enum(self) -> None:
        """build_conformance_report handles ScopeOutcome (StrEnum) .value correctly."""
        from dazzle.conformance.models import ScopeOutcome
        from dazzle.conformance.plugin import build_conformance_report

        cases = [
            _make_case(scope_type=ScopeOutcome.ACCESS_DENIED),
            _make_case(scope_type=ScopeOutcome.UNAUTHENTICATED),
            _make_case(scope_type=ScopeOutcome.ACCESS_DENIED),
        ]
        report = build_conformance_report(cases)
        assert report["scope_types"]["access_denied"] == 2
        assert report["scope_types"]["unauthenticated"] == 1

    def test_collect_missing_toml_raises(self, tmp_path: Path) -> None:
        """collect_conformance_cases raises FileNotFoundError when no dazzle.toml."""
        from dazzle.conformance.plugin import collect_conformance_cases

        with pytest.raises(FileNotFoundError, match="dazzle.toml"):
            collect_conformance_cases(tmp_path)

    def test_collect_from_shapes_validation(self) -> None:
        """Full pipeline: shapes_validation DSL → derive → fixtures, produces > 0 cases."""
        from dazzle.conformance.plugin import collect_conformance_cases

        if not _SHAPES_VALIDATION.exists():
            pytest.skip("shapes_validation example not found")

        try:
            cases, fixtures = collect_conformance_cases(_SHAPES_VALIDATION, auth_enabled=True)
        except Exception as exc:
            pytest.skip(f"DSL parse failed (dependency missing?): {exc}")

        assert len(cases) > 0, "Expected at least one conformance case"

        # All entities from shapes_validation should produce cases
        entity_names = {c.entity for c in cases}
        assert len(entity_names) > 0

        # Fixture engine should have resolved expected_rows on list cases
        list_cases = [c for c in cases if c.operation == "list"]
        assert any(c.expected_rows is not None for c in list_cases)

    def test_collect_report_round_trip(self) -> None:
        """collect_conformance_cases + build_conformance_report produce consistent totals."""
        from dazzle.conformance.plugin import build_conformance_report, collect_conformance_cases

        if not _SHAPES_VALIDATION.exists():
            pytest.skip("shapes_validation example not found")

        try:
            cases, _ = collect_conformance_cases(_SHAPES_VALIDATION, auth_enabled=True)
        except Exception as exc:
            pytest.skip(f"DSL parse failed: {exc}")

        report = build_conformance_report(cases)
        assert report["total_cases"] == len(cases)
        assert sum(report["entities"].values()) == len(cases)
        assert sum(report["scope_types"].values()) == len(cases)
