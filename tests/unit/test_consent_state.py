"""Tests for dazzle.compliance.analytics.consent (v0.61.0 Phase 2)."""

from __future__ import annotations

import pytest

from dazzle.compliance.analytics.consent import (
    CONSENT_COOKIE_VERSION,
    ConsentDefaults,
    build_decided_state,
    parse_consent_cookie,
)


class TestConsentDefaults:
    def test_eu_denies(self) -> None:
        d = ConsentDefaults.for_jurisdiction("EU")
        assert d.analytics == "denied"
        assert d.advertising == "denied"
        assert d.personalization == "denied"
        # Functional is always granted — required for service to work.
        assert d.functional == "granted"

    def test_uk_denies(self) -> None:
        assert ConsentDefaults.for_jurisdiction("UK").analytics == "denied"
        assert ConsentDefaults.for_jurisdiction("GB").analytics == "denied"

    def test_us_grants(self) -> None:
        d = ConsentDefaults.for_jurisdiction("US")
        assert d.analytics == "granted"
        assert d.advertising == "granted"
        assert d.personalization == "granted"

    def test_apac_grants(self) -> None:
        d = ConsentDefaults.for_jurisdiction("APAC")
        assert d.analytics == "granted"

    def test_individual_eea_countries_deny(self) -> None:
        # Any EEA country maps to denied defaults.
        for code in ("DE", "FR", "ES", "IT", "NL", "SE"):
            assert ConsentDefaults.for_jurisdiction(code).analytics == "denied"

    def test_none_jurisdiction_defaults_to_deny(self) -> None:
        # Safe default: treat unknown as EU.
        assert ConsentDefaults.for_jurisdiction(None).analytics == "denied"

    def test_override_denied_wins_over_us_default(self) -> None:
        d = ConsentDefaults.for_jurisdiction("US", override="denied")
        assert d.analytics == "denied"
        assert d.advertising == "denied"

    def test_override_granted_wins_over_eu_default(self) -> None:
        d = ConsentDefaults.for_jurisdiction("EU", override="granted")
        assert d.analytics == "granted"
        assert d.advertising == "granted"

    def test_undecided_state_preserves_defaults(self) -> None:
        eu_defaults = ConsentDefaults.for_jurisdiction("EU")
        state = eu_defaults.to_undecided_state()
        assert state.undecided is True
        assert state.analytics == "denied"
        assert state.functional == "granted"


class TestConsentStateSerialization:
    def test_round_trip(self) -> None:
        decided = build_decided_state(
            analytics=True, advertising=False, personalization=True, functional=True, now=12345
        )
        assert not decided.undecided
        cookie = decided.serialize()
        parsed = parse_consent_cookie(cookie, ConsentDefaults.for_jurisdiction("EU"))
        assert parsed.analytics == "granted"
        assert parsed.advertising == "denied"
        assert parsed.personalization == "granted"
        assert parsed.functional == "granted"
        assert parsed.undecided is False
        assert parsed.decided_at == 12345

    def test_empty_cookie_falls_back_to_defaults(self) -> None:
        eu = ConsentDefaults.for_jurisdiction("EU")
        s = parse_consent_cookie("", eu)
        assert s.undecided
        assert s.analytics == "denied"

    def test_none_cookie_falls_back(self) -> None:
        s = parse_consent_cookie(None, ConsentDefaults.for_jurisdiction("US"))
        assert s.undecided
        assert s.analytics == "granted"

    def test_malformed_cookie_falls_back(self) -> None:
        s = parse_consent_cookie("not json", ConsentDefaults.for_jurisdiction("EU"))
        assert s.undecided

    def test_wrong_version_falls_back(self) -> None:
        bad = '{"v":1,"a":"granted","d":"granted","p":"granted","f":"granted"}'
        s = parse_consent_cookie(bad, ConsentDefaults.for_jurisdiction("EU"))
        assert s.undecided

    def test_invalid_choice_value_falls_back(self) -> None:
        bad = (
            f'{{"v":{CONSENT_COOKIE_VERSION},"a":"maybe","d":"denied","p":"denied","f":"granted"}}'
        )
        s = parse_consent_cookie(bad, ConsentDefaults.for_jurisdiction("EU"))
        assert s.undecided

    def test_non_object_cookie_falls_back(self) -> None:
        s = parse_consent_cookie("[1, 2, 3]", ConsentDefaults.for_jurisdiction("EU"))
        assert s.undecided


class TestConsentModeV2Mapping:
    def test_granted_all_maps_to_granted_signals(self) -> None:
        state = build_decided_state(
            analytics=True, advertising=True, personalization=True, functional=True
        )
        cm = state.to_consent_mode_v2()
        assert cm["analytics_storage"] == "granted"
        assert cm["ad_storage"] == "granted"
        assert cm["ad_user_data"] == "granted"
        assert cm["ad_personalization"] == "granted"
        assert cm["functionality_storage"] == "granted"
        assert cm["security_storage"] == "granted"

    def test_denied_all_maps_to_denied_except_security(self) -> None:
        state = build_decided_state(
            analytics=False, advertising=False, personalization=False, functional=True
        )
        cm = state.to_consent_mode_v2()
        assert cm["analytics_storage"] == "denied"
        assert cm["ad_storage"] == "denied"
        # security_storage is always granted (essential).
        assert cm["security_storage"] == "granted"

    def test_advertising_denied_collapses_ad_personalization(self) -> None:
        """If advertising is denied, ad_personalization is denied even if
        personalization is granted — ad_personalization sits under the
        advertising category gate."""
        state = build_decided_state(
            analytics=True, advertising=False, personalization=True, functional=True
        )
        cm = state.to_consent_mode_v2()
        assert cm["ad_personalization"] == "denied"


class TestIsGranted:
    def test_category_lookup(self) -> None:
        state = build_decided_state(
            analytics=True, advertising=False, personalization=True, functional=True
        )
        assert state.is_granted("analytics") is True
        assert state.is_granted("advertising") is False
        assert state.is_granted("personalization") is True
        assert state.is_granted("functional") is True

    def test_unknown_category_raises(self) -> None:
        state = build_decided_state(
            analytics=True, advertising=False, personalization=True, functional=True
        )
        with pytest.raises(ValueError):
            state.is_granted("mystery")

    def test_enum_input(self) -> None:
        from dazzle.core.ir import ConsentCategory

        state = build_decided_state(
            analytics=True, advertising=False, personalization=True, functional=True
        )
        assert state.is_granted(ConsentCategory.ANALYTICS) is True
        assert state.is_granted(ConsentCategory.ADVERTISING) is False
