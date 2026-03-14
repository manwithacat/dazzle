"""Tests for pulse health radar scoring functions.

Validates that _security_score correctly treats default-deny as secure.
"""

from __future__ import annotations

from dazzle.mcp.server.handlers.pulse import _security_score


class TestSecurityScore:
    """_security_score should count default-deny as a deliberate (secure) posture."""

    def test_all_default_deny_is_100(self):
        """An app that denies everything by default is fully secured."""
        policy = {
            "summary": {
                "total_combinations": 10,
                "allow": 0,
                "explicit_deny": 0,
                "default_deny": 10,
            }
        }
        assert _security_score(policy) == 100.0

    def test_mixed_allow_and_default_deny(self):
        """allow + default_deny = full coverage."""
        policy = {
            "summary": {
                "total_combinations": 10,
                "allow": 3,
                "explicit_deny": 0,
                "default_deny": 7,
            }
        }
        assert _security_score(policy) == 100.0

    def test_partial_coverage_with_gaps(self):
        """Only explicit allow with no deny at all → partial score."""
        policy = {
            "summary": {
                "total_combinations": 10,
                "allow": 3,
                "explicit_deny": 0,
                "default_deny": 0,
            }
        }
        assert _security_score(policy) == 30.0

    def test_zero_combinations(self):
        policy = {"summary": {"total_combinations": 0}}
        assert _security_score(policy) == 0.0

    def test_empty_summary(self):
        policy = {"summary": {}}
        assert _security_score(policy) == 0.0

    def test_all_three_types(self):
        """All three types of coverage contribute."""
        policy = {
            "summary": {
                "total_combinations": 20,
                "allow": 5,
                "explicit_deny": 3,
                "default_deny": 12,
            }
        }
        assert _security_score(policy) == 100.0
