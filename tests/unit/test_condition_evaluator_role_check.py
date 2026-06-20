"""
Tests for role_check handling in the condition evaluator.

Covers:
- evaluate_condition with role_check (true/false)
- Empty/missing roles
- role_check combined with AND/OR
- condition_to_sql_filter with role_check (satisfied → empty, denied → sentinel)
- role_check in AND with comparison for SQL filter
"""

import pytest

from dazzle.http.runtime.condition_evaluator import (
    condition_to_sql_filter,
    evaluate_condition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _role_check_cond(role_name: str) -> dict:
    return {"role_check": {"role_name": role_name}}


def _comparison_cond(field: str, value: str) -> dict:
    return {
        "comparison": {
            "field": field,
            "operator": "eq",
            "value": {"literal": value},
        }
    }


def _and_cond(left: dict, right: dict) -> dict:
    return {"operator": "and", "left": left, "right": right}


def _or_cond(left: dict, right: dict) -> dict:
    return {"operator": "or", "left": left, "right": right}


# ---------------------------------------------------------------------------
# evaluate_condition — role_check
# ---------------------------------------------------------------------------


class TestEvaluateConditionRoleCheck:
    @pytest.mark.parametrize(
        ("cond", "context", "expected"),
        [
            (_role_check_cond("admin"), {"user_roles": ["admin", "viewer"]}, True),
            (_role_check_cond("admin"), {"user_roles": ["viewer"]}, False),
            (_role_check_cond("admin"), {"user_roles": []}, False),
            (_role_check_cond("admin"), {}, False),
            ({"role_check": {"role_name": ""}}, {"user_roles": ["admin"]}, False),
            ({"role_check": {}}, {"user_roles": ["admin"]}, False),
            (_role_check_cond("adm"), {"user_roles": ["admin"]}, False),
        ],
        ids=[
            "test_role_check_true_when_user_has_role",
            "test_role_check_false_when_user_lacks_role",
            "test_role_check_false_with_empty_roles_list",
            "test_role_check_false_with_missing_user_roles_key",
            "test_role_check_false_with_empty_role_name",
            "test_role_check_false_with_missing_role_name_key",
            "test_role_check_exact_match_only",
        ],
    )
    def test_role_check_evaluation(self, cond: dict, context: dict, expected: bool) -> None:
        assert evaluate_condition(cond, {}, context) is expected


# ---------------------------------------------------------------------------
# evaluate_condition — role_check combined with AND / OR
# ---------------------------------------------------------------------------


class TestEvaluateConditionRoleCheckCompound:
    @pytest.mark.parametrize(
        ("cond", "record", "context", "expected"),
        [
            # AND: role passes + comparison passes → True.
            (
                _and_cond(_role_check_cond("editor"), _comparison_cond("status", "active")),
                {"status": "active"},
                {"user_roles": ["editor"]},
                True,
            ),
            # AND: role passes + comparison fails → False.
            (
                _and_cond(_role_check_cond("editor"), _comparison_cond("status", "active")),
                {"status": "draft"},
                {"user_roles": ["editor"]},
                False,
            ),
            # AND: role fails + comparison passes → False.
            (
                _and_cond(_role_check_cond("admin"), _comparison_cond("status", "active")),
                {"status": "active"},
                {"user_roles": ["viewer"]},
                False,
            ),
            # OR: role passes + comparison fails → True.
            (
                _or_cond(_role_check_cond("admin"), _comparison_cond("status", "active")),
                {"status": "draft"},
                {"user_roles": ["admin"]},
                True,
            ),
            # OR: role fails + comparison passes → True.
            (
                _or_cond(_role_check_cond("admin"), _comparison_cond("status", "active")),
                {"status": "active"},
                {"user_roles": ["viewer"]},
                True,
            ),
            # OR: both fail → False.
            (
                _or_cond(_role_check_cond("admin"), _comparison_cond("status", "active")),
                {"status": "draft"},
                {"user_roles": ["viewer"]},
                False,
            ),
            # AND two role checks: only one role present → False.
            (
                _and_cond(_role_check_cond("editor"), _role_check_cond("reviewer")),
                {},
                {"user_roles": ["editor"]},
                False,
            ),
            # AND two role checks: both roles present → True.
            (
                _and_cond(_role_check_cond("editor"), _role_check_cond("reviewer")),
                {},
                {"user_roles": ["editor", "reviewer"]},
                True,
            ),
        ],
        ids=[
            "test_and_role_and_comparison_both_pass",
            "test_and_role_passes_comparison_fails",
            "test_and_role_fails_comparison_passes",
            "test_or_role_passes_other_fails",
            "test_or_role_fails_other_passes",
            "test_or_both_fail",
            "test_and_two_role_checks_both_required",
            "test_and_two_role_checks_both_present",
        ],
    )
    def test_evaluate_condition_compound(
        self, cond: dict, record: dict, context: dict, expected: bool
    ) -> None:
        """evaluate_condition handles AND/OR combinations of role_check and comparison."""
        assert evaluate_condition(cond, record, context) is expected


# ---------------------------------------------------------------------------
# condition_to_sql_filter — role_check
# ---------------------------------------------------------------------------


class TestConditionToSqlFilterRoleCheck:
    def test_role_satisfied_returns_empty_filters(self) -> None:
        cond = _role_check_cond("admin")
        context = {"user_roles": ["admin"]}
        result = condition_to_sql_filter(cond, context)
        assert result == {}

    def test_role_denied_returns_sentinel(self) -> None:
        cond = _role_check_cond("admin")
        context = {"user_roles": ["viewer"]}
        result = condition_to_sql_filter(cond, context)
        assert "_role_denied" in result
        assert result["_role_denied"] is True

    def test_role_denied_with_empty_roles(self) -> None:
        cond = _role_check_cond("admin")
        context = {"user_roles": []}
        result = condition_to_sql_filter(cond, context)
        assert "_role_denied" in result

    def test_role_denied_with_missing_roles_key(self) -> None:
        cond = _role_check_cond("admin")
        context = {}
        result = condition_to_sql_filter(cond, context)
        assert "_role_denied" in result

    def test_role_satisfied_in_and_with_comparison(self) -> None:
        """Role satisfied + comparison → only the comparison filter is present."""
        cond = _and_cond(
            _role_check_cond("admin"),
            _comparison_cond("owner_id", "user-123"),
        )
        context = {"user_roles": ["admin"]}
        result = condition_to_sql_filter(cond, context)
        assert "_role_denied" not in result
        assert result.get("owner_id") == "user-123"

    def test_role_denied_in_and_with_comparison_has_sentinel(self) -> None:
        """Role denied + comparison → sentinel must be present somewhere in merged dict."""
        cond = _and_cond(
            _role_check_cond("admin"),
            _comparison_cond("owner_id", "user-123"),
        )
        context = {"user_roles": ["viewer"]}
        result = condition_to_sql_filter(cond, context)
        # The AND merge does not short-circuit, so sentinel may be merged with
        # the comparison filter.  We assert the sentinel is present.
        assert "_role_denied" in result
