# tests/unit/test_condition_evaluator_grant_check.py
"""Tests for grant_check evaluation in condition evaluator."""

from datetime import UTC, datetime, timedelta

import pytest

from dazzle.http.runtime.condition_evaluator import evaluate_condition


def _make_grant(relation: str, scope_id: str, expires_at=None):
    """Create a grant-like dict matching what list_grants returns."""
    return {
        "relation": relation,
        "scope_id": scope_id,
        "status": "active",
        "expires_at": expires_at,
    }


_GRANT_CONDITION = {"grant_check": {"relation": "acting_hod", "scope_field": "department_id"}}


class TestGrantCheckEvaluation:
    """Test grant_check condition evaluation with various grant/record/context combinations."""

    @pytest.mark.parametrize(
        "record,context,expected",
        [
            (  # test_grant_check_true: matching relation and scope
                {"department_id": "dept-1"},
                {"active_grants": [_make_grant("acting_hod", "dept-1")]},
                True,
            ),
            (  # test_grant_check_false_wrong_relation: grant has different relation
                {"department_id": "dept-1"},
                {"active_grants": [_make_grant("observer", "dept-1")]},
                False,
            ),
            (  # test_grant_check_false_wrong_scope: grant covers different scope_id
                {"department_id": "dept-1"},
                {"active_grants": [_make_grant("acting_hod", "dept-2")]},
                False,
            ),
            (  # test_grant_check_false_no_grants: empty grants list
                {"department_id": "dept-1"},
                {"active_grants": []},
                False,
            ),
            (  # test_grant_check_false_no_grants_key: active_grants key absent
                {"department_id": "dept-1"},
                {},
                False,
            ),
            (  # test_grant_check_false_missing_scope_field: record lacks the scope field
                {},
                {"active_grants": [_make_grant("acting_hod", "dept-1")]},
                False,
            ),
        ],
        ids=[
            "test_grant_check_true",
            "test_grant_check_false_wrong_relation",
            "test_grant_check_false_wrong_scope",
            "test_grant_check_false_no_grants",
            "test_grant_check_false_no_grants_key",
            "test_grant_check_false_missing_scope_field",
        ],
    )
    def test_grant_check(self, record: dict, context: dict, expected: bool) -> None:
        assert evaluate_condition(_GRANT_CONDITION, record, context) is expected

    def test_grant_check_expired_grant_excluded(self):
        record = {"department_id": "dept-1"}
        expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1", expires_at=expired)],
        }
        assert evaluate_condition(_GRANT_CONDITION, record, context) is False

    def test_grant_check_future_expiry_included(self):
        record = {"department_id": "dept-1"}
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1", expires_at=future)],
        }
        assert evaluate_condition(_GRANT_CONDITION, record, context) is True

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
