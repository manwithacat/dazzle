"""#1298: per-limit env overrides + raised `standard` api_limit default.

The `standard` profile's old `api_limit=60/minute` self-429'd a single user
because SSR list/workspace pages fan out several client API XHRs per view.
The fix raised the default to 300/minute and added `DAZZLE_RATE_LIMIT_*` env
overrides so a deploy can tune any single limit without dropping to `basic`
(which would also disable CSP/HSTS/require-auth and open CORS).
"""

from __future__ import annotations

import pytest

from dazzle.http.runtime.rate_limit import (
    RateLimitConfig,
    _apply_env_limit_overrides,
    _normalize_rate_string,
    _valid_rate_string,
    configure_rate_limits_for_profile,
)

# ── raised default ────────────────────────────────────────────────────────


def test_standard_api_limit_raised_to_300() -> None:
    """The standard profile's api_limit default is 300/minute (#1298)."""
    assert configure_rate_limits_for_profile("standard").api_limit == "300/minute"


def test_strict_still_no_looser_than_standard() -> None:
    """ASVS V13.2.2 ordering must survive the bump: strict <= standard."""
    standard = configure_rate_limits_for_profile("standard")
    strict = configure_rate_limits_for_profile("strict")
    assert int(strict.api_limit.split("/")[0]) <= int(standard.api_limit.split("/")[0])


def test_basic_still_unlimited() -> None:
    """Basic profile remains limit-free (development use)."""
    assert configure_rate_limits_for_profile("basic").api_limit is None


# ── rate-string validation ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["300/minute", "5/second", "100/hour", "10/day", "300/minutes", " 60 / minute "],
)
def test_valid_rate_strings(value: str) -> None:
    assert _valid_rate_string(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "300",
        "/minute",
        "abc/minute",
        "0/minute",
        "-5/minute",
        "300/fortnight",
        "300/min/ute",
        "٣٠٠/minute",  # Arabic-Indic digits: isdigit() True but not ASCII → reject
    ],
)
def test_invalid_rate_strings(value: str) -> None:
    assert _valid_rate_string(value) is False


@pytest.mark.parametrize(
    ("value", "canonical"),
    [
        ("300/minute", "300/minute"),
        ("300/minutes", "300/minute"),  # plural tolerated → stored singular
        (" 60 / minute ", "60/minute"),  # whitespace stripped
        ("007/hour", "7/hour"),  # leading zeros normalised
        ("nope", None),
    ],
)
def test_normalize_rate_string_canonicalises(value: str, canonical: str | None) -> None:
    """A tolerated-but-noncanonical value must be stored in the canonical
    singular form slowapi definitely parses — not the raw input (#1298, so a
    typo'd plural never reaches the limiter to crash at decoration time)."""
    assert _normalize_rate_string(value) == canonical


# ── env overrides ─────────────────────────────────────────────────────────


def test_env_override_applies_valid_api_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_API", "500/minute")
    config = configure_rate_limits_for_profile("standard")
    _apply_env_limit_overrides(config)
    assert config.api_limit == "500/minute"


def test_env_override_ignores_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unparseable override is dropped — the profile default stands."""
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_API", "lots/minute")
    config = configure_rate_limits_for_profile("standard")
    _apply_env_limit_overrides(config)
    assert config.api_limit == "300/minute"


def test_env_override_unset_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "DAZZLE_RATE_LIMIT_API",
        "DAZZLE_RATE_LIMIT_AUTH",
        "DAZZLE_RATE_LIMIT_UPLOAD",
        "DAZZLE_RATE_LIMIT_2FA",
    ):
        monkeypatch.delenv(var, raising=False)
    config = configure_rate_limits_for_profile("standard")
    _apply_env_limit_overrides(config)
    assert config.api_limit == "300/minute"
    assert config.auth_limit == "10/minute"


def test_env_override_covers_all_four_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_API", "400/minute")
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_AUTH", "20/minute")
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_UPLOAD", "15/minute")
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_2FA", "8/minute")
    config = configure_rate_limits_for_profile("standard")
    _apply_env_limit_overrides(config)
    assert config.api_limit == "400/minute"
    assert config.auth_limit == "20/minute"
    assert config.upload_limit == "15/minute"
    assert config.twofa_limit == "8/minute"


def test_env_override_stores_canonical_not_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tolerated plural/whitespace override is stored canonical, so it never
    reaches slowapi as a string that could crash at route-decoration time."""
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_API", " 450 / minutes ")
    config = configure_rate_limits_for_profile("standard")
    _apply_env_limit_overrides(config, "standard")
    assert config.api_limit == "450/minute"


def test_env_override_can_lower_a_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overrides tune in both directions — a stricter deploy can lower the API limit."""
    monkeypatch.setenv("DAZZLE_RATE_LIMIT_API", "30/minute")
    config = RateLimitConfig(api_limit="300/minute")
    _apply_env_limit_overrides(config)
    assert config.api_limit == "30/minute"
