"""Tests for the connection live-reachability probe (#1342 — doctor --probe).

The probe's network I/O is injected (``http_get``), so these need no network. The SSRF gate
itself (``saml_metadata.validate_metadata_url``) is covered by ``test_saml_metadata*`` and is
reused, not re-tested here.
"""

import json
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.connection_probe import ProbeError, probe_connection


def _conn(conn_type, **config):
    return SimpleNamespace(type=conn_type, config=config)


def _gives(status, body=b""):
    """An http_get that always returns (status, body) and records the URLs it saw."""
    calls = []

    def http_get(url):
        calls.append(url)
        return status, body

    http_get.calls = calls
    return http_get


def _raises(reason):
    def http_get(url):
        raise ProbeError(reason, f"boom: {reason}")

    return http_get


_OIDC_DOC = json.dumps(
    {
        "authorization_endpoint": "https://idp.test/authorize",
        "token_endpoint": "https://idp.test/token",
        "jwks_uri": "https://idp.test/jwks",
    }
).encode()


# ---- OIDC ----


def test_oidc_discovery_ok_from_issuer():
    http_get = _gives(200, _OIDC_DOC)
    checks = probe_connection(_conn("oidc", issuer="https://idp.test"), http_get=http_get)
    assert len(checks) == 1 and checks[0].status == "ok"
    # derived the standard discovery URL from the issuer
    assert http_get.calls == ["https://idp.test/.well-known/openid-configuration"]


def test_oidc_discovery_url_overrides_issuer():
    http_get = _gives(200, _OIDC_DOC)
    probe_connection(
        _conn("oidc", issuer="https://idp.test", discovery_url="https://idp.test/custom/.wk"),
        http_get=http_get,
    )
    assert http_get.calls == ["https://idp.test/custom/.wk"]


@pytest.mark.parametrize(
    ("status", "body", "expected_substring"),
    [
        pytest.param(404, b"", "404", id="non-200"),
        pytest.param(
            200,
            json.dumps({"authorization_endpoint": "https://idp.test/authorize"}).encode(),
            "token_endpoint",
            id="missing-endpoint",
        ),
        pytest.param(200, b"<html>nope", "not valid JSON", id="not-json"),
        # a malicious/misconfigured IdP serves valid JSON that isn't an object —
        # must warn, not crash
        pytest.param(200, b"[]", "not an object", id="json-not-an-object"),
    ],
)
def test_oidc_discovery_bad_response_warns(status: int, body: bytes, expected_substring: str):
    checks = probe_connection(
        _conn("oidc", issuer="https://idp.test"), http_get=_gives(status, body)
    )
    assert checks[0].status == "warn" and expected_substring in checks[0].detail


def test_oidc_no_issuer_or_discovery_warns_without_network():
    http_get = _gives(200, _OIDC_DOC)
    checks = probe_connection(_conn("oidc"), http_get=http_get)
    assert checks[0].status == "warn" and http_get.calls == []


def test_oidc_unreachable_warns_with_reason():
    checks = probe_connection(
        _conn("oidc", issuer="https://idp.test"), http_get=_raises("unreachable")
    )
    assert checks[0].status == "warn" and "unreachable" in checks[0].detail


def test_oidc_ssrf_reject_surfaces_as_warn_not_raise():
    # validate_metadata_url would raise SamlMetadataError("private_ip"); _default_http_get maps it
    # to ProbeError. probe_connection must turn it into a warn, never propagate.
    checks = probe_connection(
        _conn("oidc", discovery_url="https://internal.local/.wk"), http_get=_raises("private_ip")
    )
    assert checks[0].status == "warn" and "private_ip" in checks[0].detail


# ---- SAML ----


def test_saml_sso_any_http_status_is_reachable():
    for status in (200, 400, 405):
        checks = probe_connection(
            _conn("saml", idp_sso_url="https://idp.test/sso"), http_get=_gives(status)
        )
        assert checks[0].name == "idp_sso_reachable"
        assert checks[0].status == "ok" and str(status) in checks[0].detail


def test_saml_sso_transport_error_is_unreachable():
    checks = probe_connection(
        _conn("saml", idp_sso_url="https://idp.test/sso"), http_get=_raises("unreachable")
    )
    assert checks[0].status == "warn" and "unreachable" in checks[0].detail


def test_saml_slo_probed_when_present():
    http_get = _gives(200)
    checks = probe_connection(
        _conn("saml", idp_sso_url="https://idp.test/sso", idp_slo_url="https://idp.test/slo"),
        http_get=http_get,
    )
    names = {c.name for c in checks}
    assert names == {"idp_sso_reachable", "idp_slo_reachable"}
    assert set(http_get.calls) == {"https://idp.test/sso", "https://idp.test/slo"}


def test_saml_no_sso_url_warns_without_network():
    http_get = _gives(200)
    checks = probe_connection(_conn("saml"), http_get=http_get)
    assert checks[0].status == "warn" and http_get.calls == []


# ---- SCIM + unknown ----


def test_scim_is_informational_no_network():
    http_get = _gives(200)
    checks = probe_connection(_conn("scim"), http_get=http_get)
    assert len(checks) == 1 and checks[0].status == "ok" and http_get.calls == []
    assert "inbound" in checks[0].detail


def test_unknown_type_warns():
    checks = probe_connection(_conn("ldap"), http_get=_gives(200))
    assert checks[0].status == "warn" and "ldap" in checks[0].detail


def test_probe_never_raises_on_non_string_config():
    # config comes from a JSONB column; a non-string issuer/sso must not crash the contract
    http_get = _gives(200, _OIDC_DOC)
    oidc = probe_connection(_conn("oidc", issuer=["not", "a", "string"]), http_get=http_get)
    assert oidc[0].status in {"ok", "warn"}  # did not raise
    saml = probe_connection(_conn("saml", idp_sso_url=12345), http_get=_gives(200))
    assert saml[0].status in {"ok", "warn"}  # did not raise


def test_all_probe_checks_are_recommended_level():
    # a probe failure must never flip the activation-ready gate (config-readiness only)
    for conn in (
        _conn("oidc", issuer="https://idp.test"),
        _conn("saml", idp_sso_url="https://idp.test/sso"),
        _conn("scim"),
    ):
        for c in probe_connection(conn, http_get=_gives(500)):
            assert c.level == "recommended"
