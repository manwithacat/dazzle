"""Tests for the connection live-reachability probe (#1342 — doctor --probe).

The probe's network I/O is injected (``http_get``), so these need no network. The SSRF gate
(``validate_probe_url``) is exercised with a stubbed resolver.
"""

import json
import socket
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth import connection_probe
from dazzle.http.runtime.auth.connection_probe import (
    ProbeError,
    probe_connection,
    validate_probe_url,
)


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
    # validate_probe_url raises ProbeError("private_ip") inside the default http_get;
    # probe_connection must turn it into a warn, never propagate.
    checks = probe_connection(
        _conn("oidc", discovery_url="https://internal.local/.wk"), http_get=_raises("private_ip")
    )
    assert checks[0].status == "warn" and "private_ip" in checks[0].detail


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
    # config comes from a JSONB column; a non-string issuer/discovery_url must not crash the contract
    http_get = _gives(200, _OIDC_DOC)
    oidc = probe_connection(_conn("oidc", issuer=["not", "a", "string"]), http_get=http_get)
    assert oidc[0].status in {"ok", "warn"}  # did not raise
    discovery = probe_connection(_conn("oidc", discovery_url=12345), http_get=_gives(200))
    assert discovery[0].status in {"ok", "warn"}  # did not raise


def test_all_probe_checks_are_recommended_level():
    # a probe failure must never flip the activation-ready gate (config-readiness only)
    for conn in (
        _conn("oidc", issuer="https://idp.test"),
        _conn("scim"),
    ):
        for c in probe_connection(conn, http_get=_gives(500)):
            assert c.level == "recommended"


# ---- SSRF gate ----


def _resolves_to(monkeypatch, *addresses):
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 443)) for a in addresses]
    monkeypatch.setattr(connection_probe.socket, "getaddrinfo", lambda *a, **k: infos)


@pytest.mark.parametrize(
    ("url", "address", "reason"),
    [
        pytest.param("http://idp.test/x", "93.184.216.34", "scheme", id="http-refused"),
        pytest.param("https://u:p@idp.test/x", "93.184.216.34", "userinfo", id="userinfo-refused"),
        pytest.param("https://idp.test\\@evil/x", "93.184.216.34", "userinfo", id="backslash"),
        pytest.param("https:///x", "93.184.216.34", "host", id="no-host"),
        pytest.param("https://idp.test/x", "127.0.0.1", "private_ip", id="loopback"),
        pytest.param("https://idp.test/x", "169.254.169.254", "private_ip", id="link-local"),
        pytest.param("https://idp.test/x", "100.64.0.1", "private_ip", id="cgnat"),
        pytest.param("https://idp.test/x", "::ffff:10.0.0.1", "private_ip", id="mapped-private"),
    ],
)
def test_validate_probe_url_rejects(monkeypatch, url, address, reason) -> None:
    _resolves_to(monkeypatch, address)
    with pytest.raises(ProbeError) as exc:
        validate_probe_url(url)
    assert exc.value.reason == reason


def test_validate_probe_url_rejects_unresolvable_host(monkeypatch) -> None:
    def _fail(*a, **k):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(connection_probe.socket, "getaddrinfo", _fail)
    with pytest.raises(ProbeError) as exc:
        validate_probe_url("https://idp.test/x")
    assert exc.value.reason == "dns"


def test_validate_probe_url_rejects_when_any_address_is_private(monkeypatch) -> None:
    _resolves_to(monkeypatch, "93.184.216.34", "10.0.0.5")
    with pytest.raises(ProbeError):
        validate_probe_url("https://idp.test/x")


def test_validate_probe_url_accepts_public_https(monkeypatch) -> None:
    _resolves_to(monkeypatch, "93.184.216.34")
    validate_probe_url("https://idp.test/.well-known/openid-configuration")
