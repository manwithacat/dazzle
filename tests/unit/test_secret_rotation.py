"""Unit tests for the secret-rotation duration parser (#1342)."""

from datetime import timedelta

import pytest

from dazzle.http.runtime.auth.secret_rotation import parse_grace_duration


def test_parse_grace_duration_units() -> None:
    assert parse_grace_duration("30m") == timedelta(minutes=30)
    assert parse_grace_duration("24h") == timedelta(hours=24)
    assert parse_grace_duration("7d") == timedelta(days=7)
    assert parse_grace_duration("2w") == timedelta(weeks=2)


@pytest.mark.parametrize(
    "bad", ["", "0h", "-1d", "24", "h", "1y", "1.5h", "24 h", "1d2h", "abc", "01h"]
)
def test_parse_grace_duration_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_grace_duration(bad)
