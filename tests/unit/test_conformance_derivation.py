"""Tests for conformance testing data models and derivation engine."""

from __future__ import annotations


class TestConformanceModels:
    def test_scope_outcome_values(self) -> None:
        from dazzle.conformance.models import ScopeOutcome

        assert ScopeOutcome.ALL == "all"
        assert ScopeOutcome.FORBIDDEN == "forbidden"
        assert ScopeOutcome.SCOPE_EXCLUDED == "scope_excluded"

    def test_conformance_case_test_id(self) -> None:
        from dazzle.conformance.models import ConformanceCase, ScopeOutcome

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
            expected_rows=1,
            scope_type=ScopeOutcome.FILTERED,
        )
        assert case.test_id == "viewer-list-Task-filtered"

    def test_conformance_case_test_id_with_row_target(self) -> None:
        from dazzle.conformance.models import ConformanceCase, ScopeOutcome

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="read",
            expected_status=200,
            row_target="own",
            scope_type=ScopeOutcome.FILTERED,
        )
        assert case.test_id == "viewer-read-Task-filtered-own"

    def test_conformance_uuid_deterministic(self) -> None:
        from dazzle.conformance.models import conformance_uuid

        a = conformance_uuid("Task", "user_a")
        b = conformance_uuid("Task", "user_a")
        c = conformance_uuid("Task", "user_b")
        assert a == b
        assert a != c

    def test_conformance_fixtures_defaults(self) -> None:
        from dazzle.conformance.models import ConformanceFixtures

        f = ConformanceFixtures()
        assert f.users == {}
        assert f.entity_rows == {}
        assert f.junction_rows == {}
        assert f.expected_counts == {}
