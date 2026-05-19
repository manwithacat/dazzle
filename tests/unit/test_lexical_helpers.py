"""Tests for ``dsl_parser_impl/_lexical.py`` (#1155).

The char-walk helpers replace four pre-existing ``re.*`` calls in the
parser. Each helper has a closed shape contract — these tests pin both
the accept and reject halves so the ADR-0024 allowlist can stay at zero.
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl._lexical import (
    extract_entity_field_prefix,
    is_short_duration_token,
    short_duration_seconds,
    split_duration_token,
)

# ─────────────── split_duration_token ───────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("30min", (30, "min")),
        ("5m", (5, "m")),
        ("24h", (24, "h")),
        ("7d", (7, "d")),
        ("2w", (2, "w")),
        ("6y", (6, "y")),
        ("1h", (1, "h")),
        ("365d", (365, "d")),
    ],
)
def test_split_duration_token_accepts(raw: str, expected: tuple[int, str]) -> None:
    assert split_duration_token(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "foo",
        "5",  # no suffix
        "min",  # no digits
        "5x",  # unknown suffix
        "5ms",  # too long
        "abc5m",  # leading non-digit
        "5 m",  # whitespace
    ],
)
def test_split_duration_token_rejects(raw: str) -> None:
    assert split_duration_token(raw) is None


def test_split_duration_token_min_precedes_m() -> None:
    """``min`` must match the 3-char suffix, not ``m`` followed by ``in``."""
    assert split_duration_token("30min") == (30, "min")
    assert split_duration_token("30m") == (30, "m")


# ─────────────── short_duration_seconds ───────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("30s", 30),
        ("5m", 300),
        ("2h", 7200),
        ("7d", 604800),
        ("0s", 0),
    ],
)
def test_short_duration_seconds_accepts(raw: str, expected: int) -> None:
    assert short_duration_seconds(raw) == expected


def test_short_duration_seconds_strips_whitespace() -> None:
    assert short_duration_seconds("  5m  ") == 300


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "5min",  # multi-char suffix not accepted here
        "5w",  # week not in short-form
        "5y",  # year not in short-form
        "foo",
        "5",
        "s",
    ],
)
def test_short_duration_seconds_rejects(raw: str) -> None:
    assert short_duration_seconds(raw) is None


# ─────────────── is_short_duration_token ───────────────


def test_is_short_duration_token_predicate() -> None:
    assert is_short_duration_token("5s")
    assert is_short_duration_token("30m")
    assert not is_short_duration_token("5min")
    assert not is_short_duration_token("signal_name")
    assert not is_short_duration_token("")


# ─────────────── extract_entity_field_prefix ───────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Invoice.status is 'draft'", "Invoice.status"),
        ("Invoice.status", "Invoice.status"),
        ("Invoice_x.status_value", "Invoice_x.status_value"),
        ("A.b", "A.b"),
        ("Entity9.field2", "Entity9.field2"),
    ],
)
def test_extract_entity_field_prefix_accepts(raw: str, expected: str) -> None:
    assert extract_entity_field_prefix(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "user.status",  # entity must start uppercase
        "Invoice.Status",  # field must start lowercase
        "User submits form",  # no dot
        ".status",  # missing entity
        "Invoice.",  # missing field
        " Invoice.status",  # leading whitespace — match-at-0 semantics
    ],
)
def test_extract_entity_field_prefix_rejects(raw: str) -> None:
    assert extract_entity_field_prefix(raw) is None


def test_extract_entity_field_prefix_stops_at_non_ident() -> None:
    """Field name greedily consumes ident chars then stops."""
    assert extract_entity_field_prefix("Invoice.status_value=draft") == ("Invoice.status_value")
