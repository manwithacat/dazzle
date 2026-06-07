"""Property/fuzz tests for the small input-boundary parsers (#1342 fuzz-leverage #3).

Each asserts the parser's *contract invariant* — arbitrary input maps to a controlled
outcome (a documented exception type OR a valid result), never a raw/unexpected crash.
These are the new fuzz surfaces the leverage evaluation identified
(`docs/proposals/fuzz-harness-leverage-evaluation.md`)."""

from __future__ import annotations

import base64
from datetime import timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---- parse_grace_duration: any str → timedelta>0 OR ValueError, never anything else ----


class TestParseGraceDuration:
    @given(st.text(max_size=50))
    @settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_text(self, s: str) -> None:
        from dazzle.back.runtime.auth.secret_rotation import parse_grace_duration

        try:
            result = parse_grace_duration(s)
        except ValueError:
            return  # documented outcome
        assert isinstance(result, timedelta) and result > timedelta(0)

    @given(st.from_regex(r"[1-9][0-9]{0,500}[mhdw]", fullmatch=True))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_form_including_huge(self, s: str) -> None:
        # A well-formed but astronomically large duration must still be ValueError,
        # not OverflowError (timedelta(weeks=10**30) overflows C int).
        from dazzle.back.runtime.auth.secret_rotation import parse_grace_duration

        try:
            assert isinstance(parse_grace_duration(s), timedelta)
        except ValueError:
            pass


# ---- parse_group_patch: SCIM-lenient — any dict → a list, never crashes ----

# SCIM-shaped values: bias the fuzzer toward the keys/strings that actually reach the
# parse branches (op/path/value/members/displayName), so it exercises real code paths
# rather than wandering random-key dicts. (Lesson from the first run: an unbiased strategy
# never drew {"Operations":[1]} etc.)
_SCIM_STR = st.sampled_from(
    ["add", "remove", "replace", "members", "displayName", 'members[value eq "x"]', "value", ""]
) | st.text(max_size=8)
_SCIM_VALUE = st.recursive(
    st.none() | st.booleans() | st.integers() | _SCIM_STR,
    lambda c: st.lists(c, max_size=4) | st.dictionaries(_SCIM_STR, c, max_size=4),
    max_leaves=10,
)
_SCIM_OP = st.one_of(
    st.dictionaries(st.sampled_from(["op", "path", "value"]), _SCIM_VALUE, max_size=3),
    st.integers(),
    st.text(max_size=5),
    st.none(),
)
_SCIM_BODY = st.dictionaries(
    st.sampled_from(["Operations", "schemas", "x"]),
    _SCIM_VALUE | st.lists(_SCIM_OP, max_size=4),
    max_size=3,
)


class TestParseGroupPatch:
    @given(_SCIM_BODY)
    @settings(max_examples=600, suppress_health_check=[HealthCheck.too_slow])
    def test_scim_shaped_body_returns_list_never_crashes(self, body: dict) -> None:
        from dazzle.back.runtime.auth.scim_provisioning import parse_group_patch

        # Contract: "unknown ops are skipped (SCIM-lenient)" → it must always return a
        # list of (op, arg) tuples and never raise on a malformed/hostile PATCH body.
        result = parse_group_patch(body)
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    @pytest.mark.parametrize(
        "body",
        [
            {"Operations": [1]},  # non-dict op
            {"Operations": "notalist"},  # Operations not a list
            {"Operations": [{"op": "add", "path": "members", "value": [1]}]},  # non-dict member
            {"Operations": [{"op": "add", "path": None, "value": {"members": [1]}}]},
            {"Operations": [{"op": "replace", "path": "members", "value": "x"}]},  # value not list
        ],
    )
    def test_malformed_ops_are_skipped_not_crashed(self, body: dict) -> None:
        from dazzle.back.runtime.auth.scim_provisioning import parse_group_patch

        assert isinstance(parse_group_patch(body), list)


# ---- connection_crypto: round-trip + tamper detection over arbitrary plaintext ----


class TestConnectionCryptoRoundTrip:
    @given(st.text(max_size=300))
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_roundtrip(self, monkeypatch, plaintext: str) -> None:
        monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())
        from dazzle.back.runtime.auth.connection_crypto import decrypt_secret, encrypt_secret

        assert decrypt_secret(encrypt_secret(plaintext)) == plaintext

    @given(st.text(max_size=100))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_tampered_token_never_silently_decrypts(self, monkeypatch, plaintext: str) -> None:
        monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())
        from dazzle.back.runtime.auth.connection_crypto import (
            ConnectionSecretError,
            decrypt_secret,
            encrypt_secret,
        )

        token = encrypt_secret(plaintext)
        # Flip the last base64 char → AES-GCM auth must reject (never return wrong plaintext).
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        try:
            assert decrypt_secret(tampered) != plaintext  # if it somehow decodes, must differ
        except (ConnectionSecretError, ValueError):
            pass  # the expected outcome: authenticated decryption refuses tampered input


# ---- validate_metadata_url: arbitrary URL → SamlMetadataError or None, never else ----


class TestValidateMetadataUrl:
    @given(st.text(max_size=120))
    @settings(
        max_examples=400,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_arbitrary_url(self, monkeypatch, url: str) -> None:
        import socket

        from dazzle.back.runtime.auth.saml_metadata import (
            SamlMetadataError,
            validate_metadata_url,
        )

        # Stub DNS to a fixed public IP so we fuzz the parse/scheme/IP-classify logic, not
        # the network. (A real getaddrinfo would be slow + nondeterministic.)
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
            ],
        )
        try:
            assert validate_metadata_url(url) is None  # passes only via the public-IP stub
        except SamlMetadataError:
            pass  # the documented rejection path


# ---- parse_idp_metadata_xml: arbitrary text → dict or SamlMetadataError (onelogin, CI) ----


class TestParseIdpMetadataXml:
    @given(st.text(max_size=400))
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_text(self, s: str) -> None:
        pytest.importorskip("onelogin")
        from dazzle.back.runtime.auth.saml_metadata import (
            SamlMetadataError,
            parse_idp_metadata_xml,
        )

        try:
            result = parse_idp_metadata_xml(s)
        except SamlMetadataError:
            return  # documented outcome (parse/incomplete/no_saml_extra)
        assert isinstance(result, dict) and "idp_entity_id" in result
