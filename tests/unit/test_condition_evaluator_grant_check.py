# tests/unit/test_condition_evaluator_grant_check.py
"""Tests for grant_check evaluation in condition evaluator."""

from datetime import UTC, datetime, timedelta

from dazzle_back.runtime.condition_evaluator import evaluate_condition


def _make_grant(relation: str, scope_id: str, expires_at=None):
    """Create a grant-like dict matching what list_grants returns."""
    return {
        "relation": relation,
        "scope_id": scope_id,
        "status": "active",
        "expires_at": expires_at,
    }


class TestGrantCheckEvaluation:
    def test_grant_check_true(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {"department_id": "dept-1"}
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is True

    def test_grant_check_false_wrong_relation(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {"department_id": "dept-1"}
        context = {
            "active_grants": [_make_grant("observer", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_wrong_scope(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {"department_id": "dept-1"}
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-2")],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_no_grants(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {"department_id": "dept-1"}
        context = {"active_grants": []}
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_no_grants_key(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {"department_id": "dept-1"}
        context = {}
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_missing_scope_field(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {}  # no department_id
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_expired_grant_excluded(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {"department_id": "dept-1"}
        expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1", expires_at=expired)],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_future_expiry_included(self):
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}
        record = {"department_id": "dept-1"}
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1", expires_at=future)],
        }
        assert evaluate_condition(condition, record, context) is True

    def test_grant_check_combined_with_role_or(self):
        """role(hod) or has_grant('acting_hod', department_id)"""
        condition = {
            "operator": "or",
            "left": {"role_check": {"role_name": "hod"}},
            "right": {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}},
        }
        record = {"department_id": "dept-1"}
        # User doesn't have hod role but has grant
        context = {
            "user_roles": [],
            "active_grants": [_make_grant("acting_hod", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is True
