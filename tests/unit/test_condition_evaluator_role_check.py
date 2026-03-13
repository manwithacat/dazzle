"""
Tests for role_check handling in the condition evaluator.

Covers:
- evaluate_condition with role_check (true/false)
- Empty/missing roles
- role_check combined with AND/OR
- condition_to_sql_filter with role_check (satisfied → empty, denied → sentinel)
- role_check in AND with comparison for SQL filter
"""

from __future__ import annotations

from dazzle_back.runtime.condition_evaluator import (
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
    def test_role_check_true_when_user_has_role(self) -> None:
        cond = _role_check_cond("admin")
        context = {"user_roles": ["admin", "viewer"]}
        assert evaluate_condition(cond, {}, context) is True

    def test_role_check_false_when_user_lacks_role(self) -> None:
        cond = _role_check_cond("admin")
        context = {"user_roles": ["viewer"]}
        assert evaluate_condition(cond, {}, context) is False

    def test_role_check_false_with_empty_roles_list(self) -> None:
        cond = _role_check_cond("admin")
        context = {"user_roles": []}
        assert evaluate_condition(cond, {}, context) is False

    def test_role_check_false_with_missing_user_roles_key(self) -> None:
        cond = _role_check_cond("admin")
        context = {}
        assert evaluate_condition(cond, {}, context) is False

    def test_role_check_false_with_empty_role_name(self) -> None:
        cond = {"role_check": {"role_name": ""}}
        context = {"user_roles": ["admin"]}
        assert evaluate_condition(cond, {}, context) is False

    def test_role_check_false_with_missing_role_name_key(self) -> None:
        cond = {"role_check": {}}
        context = {"user_roles": ["admin"]}
        assert evaluate_condition(cond, {}, context) is False

    def test_role_check_exact_match_only(self) -> None:
        """'adm' should not match 'admin'."""
        cond = _role_check_cond("adm")
        context = {"user_roles": ["admin"]}
        assert evaluate_condition(cond, {}, context) is False


# ---------------------------------------------------------------------------
# evaluate_condition — role_check combined with AND / OR
# ---------------------------------------------------------------------------


class TestEvaluateConditionRoleCheckCompound:
    def test_and_role_and_comparison_both_pass(self) -> None:
        cond = _and_cond(
            _role_check_cond("editor"),
            _comparison_cond("status", "active"),
        )
        context = {"user_roles": ["editor"]}
        record = {"status": "active"}
        assert evaluate_condition(cond, record, context) is True

    def test_and_role_passes_comparison_fails(self) -> None:
        cond = _and_cond(
            _role_check_cond("editor"),
            _comparison_cond("status", "active"),
        )
        context = {"user_roles": ["editor"]}
        record = {"status": "draft"}
        assert evaluate_condition(cond, record, context) is False

    def test_and_role_fails_comparison_passes(self) -> None:
        cond = _and_cond(
            _role_check_cond("admin"),
            _comparison_cond("status", "active"),
        )
        context = {"user_roles": ["viewer"]}
        record = {"status": "active"}
        assert evaluate_condition(cond, record, context) is False

    def test_or_role_passes_other_fails(self) -> None:
        cond = _or_cond(
            _role_check_cond("admin"),
            _comparison_cond("status", "active"),
        )
        context = {"user_roles": ["admin"]}
        record = {"status": "draft"}
        assert evaluate_condition(cond, record, context) is True

    def test_or_role_fails_other_passes(self) -> None:
        cond = _or_cond(
            _role_check_cond("admin"),
            _comparison_cond("status", "active"),
        )
        context = {"user_roles": ["viewer"]}
        record = {"status": "active"}
        assert evaluate_condition(cond, record, context) is True

    def test_or_both_fail(self) -> None:
        cond = _or_cond(
            _role_check_cond("admin"),
            _comparison_cond("status", "active"),
        )
        context = {"user_roles": ["viewer"]}
        record = {"status": "draft"}
        assert evaluate_condition(cond, record, context) is False

    def test_and_two_role_checks_both_required(self) -> None:
        cond = _and_cond(
            _role_check_cond("editor"),
            _role_check_cond("reviewer"),
        )
        context = {"user_roles": ["editor"]}
        assert evaluate_condition(cond, {}, context) is False

    def test_and_two_role_checks_both_present(self) -> None:
        cond = _and_cond(
            _role_check_cond("editor"),
            _role_check_cond("reviewer"),
        )
        context = {"user_roles": ["editor", "reviewer"]}
        assert evaluate_condition(cond, {}, context) is True


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
