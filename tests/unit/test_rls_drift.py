"""Unit tests for the shape-based RLS drift comparison (Phase D Task 4).

These exercise the pure, DB-free comparison core (``compare_table_policies``)
with a synthetic expected-descriptor list and fake live ``pg_policies`` rows.
The real-PG end-to-end proof (apply + idempotency + drift-detected) lives in
``tests/integration/test_rls_apply_and_drift_pg.py``.
"""

from __future__ import annotations

import pytest

from dazzle.db.rls_drift import compare_table_policies
from dazzle.http.runtime.rls_schema import PolicyDescriptor

pytestmark = pytest.mark.gate


def _fence() -> PolicyDescriptor:
    return PolicyDescriptor(
        entity="Project", name="tenant_fence", cmd="ALL", permissive=False, source="framework"
    )


def _scope_select() -> PolicyDescriptor:
    return PolicyDescriptor(
        entity="Project", name="scope_select", cmd="SELECT", permissive=True, source="scope-rule"
    )


def _live(name: str, cmd: str, permissive: str) -> dict[str, object]:
    return {"policyname": name, "cmd": cmd, "permissive": permissive}


def test_no_drift_on_exact_match() -> None:
    """RLS enabled+forced and the live policy set matches the expected shape
    exactly → no issues."""
    expected = [_fence(), _scope_select()]
    live = [
        _live("tenant_fence", "ALL", "RESTRICTIVE"),
        _live("scope_select", "SELECT", "PERMISSIVE"),
    ]
    issues = compare_table_policies("Project", expected, live, rls_enabled=True, rls_forced=True)
    assert issues == []


def test_rls_disabled_is_drift() -> None:
    expected = [_fence()]
    live = [_live("tenant_fence", "ALL", "RESTRICTIVE")]
    issues = compare_table_policies("Project", expected, live, rls_enabled=False, rls_forced=True)
    assert any("not enabled" in i for i in issues)


def test_rls_not_forced_is_drift() -> None:
    expected = [_fence()]
    live = [_live("tenant_fence", "ALL", "RESTRICTIVE")]
    issues = compare_table_policies("Project", expected, live, rls_enabled=True, rls_forced=False)
    assert any("not forced" in i for i in issues)


def test_missing_expected_policy_is_drift() -> None:
    """A dropped fence is reported as a missing expected policy."""
    expected = [_fence(), _scope_select()]
    live = [_live("scope_select", "SELECT", "PERMISSIVE")]  # fence dropped
    issues = compare_table_policies("Project", expected, live, rls_enabled=True, rls_forced=True)
    assert any("missing expected policy 'tenant_fence'" in i for i in issues)
    # The present scope policy is NOT flagged.
    assert not any("scope_select" in i for i in issues)


def test_unexpected_extra_policy_is_drift() -> None:
    expected = [_fence()]
    live = [
        _live("tenant_fence", "ALL", "RESTRICTIVE"),
        _live("rogue_policy", "ALL", "PERMISSIVE"),
    ]
    issues = compare_table_policies("Project", expected, live, rls_enabled=True, rls_forced=True)
    assert any("unexpected policy 'rogue_policy'" in i for i in issues)


def test_wrong_shape_for_existing_policy_is_drift() -> None:
    """An expected policy name present but with the wrong permissive flag is a
    shape mismatch (not a clean match, not a plain 'missing')."""
    expected = [_fence()]
    # tenant_fence present but PERMISSIVE instead of RESTRICTIVE.
    live = [_live("tenant_fence", "ALL", "PERMISSIVE")]
    issues = compare_table_policies("Project", expected, live, rls_enabled=True, rls_forced=True)
    assert any("wrong shape" in i and "tenant_fence" in i for i in issues)


def test_permissive_text_and_bool_both_accepted() -> None:
    """The live permissive flag may arrive as 'PERMISSIVE' text or a bool; both
    normalise to the same shape (no false drift from a coercing driver)."""
    expected = [_scope_select()]
    live_text = [_live("scope_select", "SELECT", "PERMISSIVE")]
    live_bool = [{"policyname": "scope_select", "cmd": "SELECT", "permissive": True}]
    assert (
        compare_table_policies("Project", expected, live_text, rls_enabled=True, rls_forced=True)
        == []
    )
    assert (
        compare_table_policies("Project", expected, live_bool, rls_enabled=True, rls_forced=True)
        == []
    )
