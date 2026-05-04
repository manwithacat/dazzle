"""Tests for pulse health radar scoring functions.

Validates that _security_score correctly treats default-deny as secure.
"""

import pytest

from dazzle.mcp.server.handlers.pulse import _security_score


class TestSecurityScore:
    """_security_score should count default-deny as a deliberate (secure) posture."""

    @pytest.mark.parametrize(
        ("summary", "expected"),
        [
            # All default-deny is fully secured (deliberate posture)
            ({"total_combinations": 10, "allow": 0, "explicit_deny": 0, "default_deny": 10}, 100.0),
            # allow + default_deny = full coverage
            ({"total_combinations": 10, "allow": 3, "explicit_deny": 0, "default_deny": 7}, 100.0),
            # Only explicit allow, no deny → partial
            ({"total_combinations": 10, "allow": 3, "explicit_deny": 0, "default_deny": 0}, 30.0),
            # All three types contribute
            (
                {"total_combinations": 20, "allow": 5, "explicit_deny": 3, "default_deny": 12},
                100.0,
            ),
            # Edge: zero combinations
            ({"total_combinations": 0}, 0.0),
            # Edge: empty summary
            ({}, 0.0),
        ],
        ids=[
            "all_default_deny_is_100",
            "mixed_allow_and_default_deny",
            "partial_coverage_with_gaps",
            "all_three_types",
            "zero_combinations",
            "empty_summary",
        ],
    )
    def test_score(self, summary, expected) -> None:
        assert _security_score({"summary": summary}) == expected
