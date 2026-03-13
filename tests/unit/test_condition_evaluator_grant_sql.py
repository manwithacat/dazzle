# tests/unit/test_condition_evaluator_grant_sql.py
"""Tests for grant_check SQL filter generation in condition_to_sql_filter."""

from dazzle_back.runtime.condition_evaluator import condition_to_sql_filter


class TestGrantCheckSqlFilter:
    def test_grant_check_generates_subquery_clause(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        context = {"current_user_id": "user-1"}
        filters = condition_to_sql_filter(condition, context)
        # Should produce a _grant_subquery key with the subquery info
        assert "_grant_subquery" in filters
        sq = filters["_grant_subquery"]
        assert sq["field"] == "department_id"
        assert sq["relation"] == "acting_hod"
        assert sq["principal_id"] == "user-1"

    def test_grant_check_no_user_returns_deny(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        context = {}  # no current_user_id
        filters = condition_to_sql_filter(condition, context)
        assert "_grant_denied" in filters

    def test_grant_check_in_or_returns_empty_for_post_filter(self):
        """OR conditions with grant_check need post-fetch filtering."""
        condition = {
            "operator": "or",
            "left": {"role_check": {"role_name": "hod"}},
            "right": {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}},
        }
        context = {"user_roles": [], "current_user_id": "user-1"}
        # OR conditions already fall through to post-fetch filtering
        # The _condition_has_or check catches this
        filters = condition_to_sql_filter(condition, context)
        # OR at top level → empty filters (rely on post-fetch)
        assert filters == {}

    def test_grant_check_in_and_with_comparison(self):
        """has_grant(...) and status = active — both become SQL filters."""
        condition = {
            "operator": "and",
            "left": {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}},
            "right": {
                "comparison": {
                    "field": "status",
                    "operator": "eq",
                    "value": {"literal": "active"},
                }
            },
        }
        context = {"current_user_id": "user-1"}
        filters = condition_to_sql_filter(condition, context)
        assert "status" in filters
        assert "_grant_subquery" in filters
