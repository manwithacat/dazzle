"""Tests for the `subprocessor` top-level DSL construct (v0.61.0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import (
    ConsentCategory,
    DataCategory,
    LegalBasis,
    SubprocessorSpec,
)


def _parse(dsl: str) -> list[SubprocessorSpec]:
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("t.dsl"))
    return list(fragment.subprocessors)


class TestSubprocessorParsing:
    def test_minimal(self) -> None:
        subs = _parse(
            """module m
app X "X"
subprocessor foo "Foo":
  handler: "Foo Inc"
  jurisdiction: US
  retention: "1 year"
  legal_basis: consent
  consent_category: analytics
"""
        )
        assert len(subs) == 1
        sp = subs[0]
        assert sp.name == "foo"
        assert sp.label == "Foo"
        assert sp.handler == "Foo Inc"
        assert sp.jurisdiction == "US"
        assert sp.legal_basis is LegalBasis.CONSENT
        assert sp.consent_category is ConsentCategory.ANALYTICS
        assert sp.cookies == []
        assert sp.data_categories == []
        assert not sp.is_framework_default

    def test_full(self) -> None:
        subs = _parse(
            """module m
app X "X"
subprocessor ga "Google Analytics":
  handler: "Google LLC"
  handler_address: "Mountain View CA"
  jurisdiction: us
  data_categories: [pseudonymous_id, page_url, session_data]
  retention: "14 months"
  legal_basis: legitimate_interest
  consent_category: analytics
  dpa_url: "https://example/dpa"
  scc_url: "https://example/sccs"
  cookies: [_ga, _ga_*, _gid]
  purpose: "web analytics"
"""
        )
        sp = subs[0]
        assert sp.jurisdiction == "US"  # validator uppercases
        assert DataCategory.PSEUDONYMOUS_ID in sp.data_categories
        assert DataCategory.PAGE_URL in sp.data_categories
        assert DataCategory.SESSION_DATA in sp.data_categories
        assert sp.cookies == ["_ga", "_ga_*", "_gid"]
        assert sp.purpose == "web analytics"
        assert sp.needs_sccs is True

    def test_multiple(self) -> None:
        subs = _parse(
            """module m
app X "X"

subprocessor ga "Google Analytics":
  handler: "Google LLC"
  jurisdiction: US
  retention: "14 months"
  legal_basis: legitimate_interest
  consent_category: analytics

subprocessor plausible "Plausible":
  handler: "Plausible OU"
  jurisdiction: EU
  retention: "indefinite"
  legal_basis: legitimate_interest
  consent_category: analytics
"""
        )
        names = {sp.name for sp in subs}
        assert names == {"ga", "plausible"}

    def test_needs_sccs_flag(self) -> None:
        us, eu = _parse(
            """module m
app X "X"

subprocessor us_proc "US Proc":
  handler: "U"
  jurisdiction: US
  retention: "1y"
  legal_basis: consent
  consent_category: analytics

subprocessor eu_proc "EU Proc":
  handler: "E"
  jurisdiction: EU
  retention: "1y"
  legal_basis: consent
  consent_category: analytics
"""
        )
        assert us.needs_sccs is True
        assert eu.needs_sccs is False


class TestSubprocessorErrors:
    def test_missing_required(self) -> None:
        with pytest.raises(ParseError, match="missing required key"):
            _parse(
                """module m
app X "X"
subprocessor foo "Foo":
  handler: "Foo"
"""
            )

    def test_unknown_key(self) -> None:
        with pytest.raises(ParseError, match="Unknown subprocessor key"):
            _parse(
                """module m
app X "X"
subprocessor foo "Foo":
  handler: "X"
  jurisdiction: US
  retention: "1y"
  legal_basis: consent
  consent_category: analytics
  bogus_key: "whatever"
"""
            )

    def test_duplicate_key(self) -> None:
        with pytest.raises(ParseError, match="Duplicate subprocessor key"):
            _parse(
                """module m
app X "X"
subprocessor foo "Foo":
  handler: "A"
  handler: "B"
  jurisdiction: US
  retention: "1y"
  legal_basis: consent
  consent_category: analytics
"""
            )

    def test_bad_legal_basis(self) -> None:
        with pytest.raises(ParseError, match="Unknown legal_basis"):
            _parse(
                """module m
app X "X"
subprocessor foo "Foo":
  handler: "X"
  jurisdiction: US
  retention: "1y"
  legal_basis: bogus
  consent_category: analytics
"""
            )

    def test_bad_consent_category(self) -> None:
        with pytest.raises(ParseError, match="Unknown consent_category"):
            _parse(
                """module m
app X "X"
subprocessor foo "Foo":
  handler: "X"
  jurisdiction: US
  retention: "1y"
  legal_basis: consent
  consent_category: mystery
"""
            )

    def test_bad_data_category(self) -> None:
        with pytest.raises(ParseError, match="Unknown data_category"):
            _parse(
                """module m
app X "X"
subprocessor foo "Foo":
  handler: "X"
  jurisdiction: US
  retention: "1y"
  legal_basis: consent
  consent_category: analytics
  data_categories: [bogus_cat]
"""
            )


class TestSubprocessorSpecValidation:
    def test_invalid_name(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SubprocessorSpec(
                name="123bad",
                label="X",
                handler="X",
                jurisdiction="US",
                retention="1y",
                legal_basis=LegalBasis.CONSENT,
                consent_category=ConsentCategory.ANALYTICS,
            )

    def test_spec_is_frozen(self) -> None:
        sp = SubprocessorSpec(
            name="ok",
            label="X",
            handler="X",
            jurisdiction="US",
            retention="1y",
            legal_basis=LegalBasis.CONSENT,
            consent_category=ConsentCategory.ANALYTICS,
        )
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            sp.handler = "Evil"  # type: ignore[misc]
