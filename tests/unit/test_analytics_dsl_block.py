"""Tests for the `analytics:` DSL block parser (v0.61.0 Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(dsl: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("t.dsl"))
    return fragment


class TestAnalyticsBlockParsing:
    def test_minimal_providers_block(self) -> None:
        fragment = _parse(
            """module t
app T "T"
analytics:
  providers:
    gtm:
      id: "GTM-XXX"
"""
        )
        assert fragment.analytics is not None
        assert len(fragment.analytics.providers) == 1
        gtm = fragment.analytics.providers[0]
        assert gtm.name == "gtm"
        assert gtm.params == {"id": "GTM-XXX"}

    def test_multiple_providers(self) -> None:
        fragment = _parse(
            """module t
app T "T"
analytics:
  providers:
    gtm:
      id: "GTM-ABC"
    plausible:
      domain: "example.com"
      script_origin: "https://plausible.example.com/js/script.js"
"""
        )
        assert fragment.analytics is not None
        names = [p.name for p in fragment.analytics.providers]
        assert names == ["gtm", "plausible"]

        plausible = fragment.analytics.providers[1]
        assert plausible.params["domain"] == "example.com"
        assert plausible.params["script_origin"].startswith("https://plausible.example.com")

    def test_consent_subsection(self) -> None:
        fragment = _parse(
            """module t
app T "T"
analytics:
  providers:
    gtm:
      id: "GTM-X"
  consent:
    default_jurisdiction: US
    consent_override: granted
"""
        )
        assert fragment.analytics is not None
        consent = fragment.analytics.consent
        assert consent is not None
        assert consent.default_jurisdiction == "US"
        assert consent.consent_override == "granted"

    def test_empty_analytics_block_allowed(self) -> None:
        """Bare `analytics:` with no children is parsed as empty spec."""
        fragment = _parse(
            """module t
app T "T"
analytics:
"""
        )
        # An empty block yields a spec with empty providers list / no consent.
        assert fragment.analytics is not None
        assert fragment.analytics.providers == []
        assert fragment.analytics.consent is None


class TestAnalyticsBlockErrors:
    def test_unknown_top_level_key(self) -> None:
        with pytest.raises(ParseError, match="Unknown analytics key"):
            _parse(
                """module t
app T "T"
analytics:
  bogus: value
"""
            )

    def test_invalid_consent_override_value(self) -> None:
        with pytest.raises(ParseError, match="consent_override must be"):
            _parse(
                """module t
app T "T"
analytics:
  consent:
    consent_override: maybe
"""
            )

    def test_unknown_consent_key(self) -> None:
        with pytest.raises(ParseError, match="Unknown consent key"):
            _parse(
                """module t
app T "T"
analytics:
  consent:
    mystery: whatever
"""
            )

    def test_duplicate_provider_name(self) -> None:
        with pytest.raises(ParseError, match="Duplicate analytics provider"):
            _parse(
                """module t
app T "T"
analytics:
  providers:
    gtm:
      id: "a"
    gtm:
      id: "b"
"""
            )

    def test_duplicate_analytics_block(self) -> None:
        """Only one analytics: block is allowed per module."""
        with pytest.raises(ParseError, match="Only one"):
            _parse(
                """module t
app T "T"
analytics:
  providers:
    gtm:
      id: "X"
analytics:
  providers:
    plausible:
      domain: "ex.com"
"""
            )


class TestIRShape:
    def test_specs_are_frozen(self) -> None:
        fragment = _parse(
            """module t
app T "T"
analytics:
  providers:
    gtm:
      id: "X"
"""
        )
        spec = fragment.analytics
        assert spec is not None
        # Pydantic frozen model.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            spec.providers = []  # type: ignore[misc]
