"""SAML IdP-metadata import: SSRF guard + fetch (local) + parse (CI: onelogin)."""

import socket

import pytest

from dazzle.back.runtime.auth.saml_metadata import (
    SamlMetadataError,
    fetch_idp_metadata,
    validate_metadata_url,
)


def _addrinfo(ip: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]


def test_validate_rejects_non_https() -> None:
    with pytest.raises(SamlMetadataError) as ei:
        validate_metadata_url("http://idp.example/metadata")
    assert ei.value.reason == "scheme"


def test_validate_rejects_private_ip(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("127.0.0.1"))
    with pytest.raises(SamlMetadataError) as ei:
        validate_metadata_url("https://localhost/metadata")
    assert ei.value.reason == "private_ip"


def test_validate_rejects_rfc1918(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("10.1.2.3"))
    with pytest.raises(SamlMetadataError):
        validate_metadata_url("https://internal.corp/metadata")


def test_validate_allows_public(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    validate_metadata_url("https://idp.example/metadata")  # no raise


def test_validate_unresolvable(monkeypatch) -> None:
    def _boom(*a, **k):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    with pytest.raises(SamlMetadataError) as ei:
        validate_metadata_url("https://nope.invalid/metadata")
    assert ei.value.reason == "dns"


def test_validate_rejects_cgnat(monkeypatch) -> None:
    # RFC 6598 Shared Address Space (100.64/10) is NOT is_private — the not-is_global
    # check must still reject it.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("100.64.1.1"))
    with pytest.raises(SamlMetadataError) as ei:
        validate_metadata_url("https://cgnat.example/metadata")
    assert ei.value.reason == "private_ip"


def test_validate_rejects_ipv4_mapped_loopback(monkeypatch) -> None:
    def _v6(*a, **k):
        return [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("::ffff:127.0.0.1", 443, 0, 0),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", _v6)
    with pytest.raises(SamlMetadataError) as ei:
        validate_metadata_url("https://mapped.example/metadata")
    assert ei.value.reason == "private_ip"


def test_validate_rejects_userinfo() -> None:
    with pytest.raises(SamlMetadataError) as ei:
        validate_metadata_url("https://user@idp.example/metadata")
    assert ei.value.reason == "userinfo"


def test_validate_rejects_backslash() -> None:
    with pytest.raises(SamlMetadataError) as ei:
        validate_metadata_url("https://idp.example\\@internal/metadata")
    assert ei.value.reason == "userinfo"


class _FakeStream:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield self._body


def test_fetch_size_capped(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    import httpx

    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream(b"x" * (1_048_576 + 1)))
    with pytest.raises(SamlMetadataError) as ei:
        fetch_idp_metadata("https://idp.example/metadata")
    assert ei.value.reason == "too_large"


def test_fetch_at_exactly_the_cap_is_allowed(monkeypatch) -> None:
    # Boundary: a body of EXACTLY the cap is OK; only > cap is rejected. (Pins the `>` vs
    # `>=` boundary — a mutation-testing survivor, #1342 fuzz-leverage #5.)
    from dazzle.back.runtime.auth.saml_metadata import _MAX_METADATA_BYTES

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    import httpx

    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream(b"x" * _MAX_METADATA_BYTES))
    assert fetch_idp_metadata("https://idp.example/metadata") == "x" * _MAX_METADATA_BYTES


def test_fetch_passes_no_redirects(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    seen: dict = {}
    import httpx

    def _stream(method, url, **kw):
        seen.update(kw)
        return _FakeStream(b"<xml/>")

    monkeypatch.setattr(httpx, "stream", _stream)
    assert fetch_idp_metadata("https://idp.example/metadata") == "<xml/>"
    assert seen["follow_redirects"] is False


def test_fetch_rejects_http_before_network(monkeypatch) -> None:
    # The validator must run before any httpx call.
    import httpx

    def _boom(*a, **k):
        raise AssertionError("httpx.stream must not be called for a non-https URL")

    monkeypatch.setattr(httpx, "stream", _boom)
    with pytest.raises(SamlMetadataError):
        fetch_idp_metadata("http://idp.example/metadata")


# ---- parser tests (CI — onelogin / [saml] extra) ----

_IDP_METADATA_XML = """<?xml version="1.0"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example/idp">
  <IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <KeyDescriptor use="signing">
      <KeyInfo xmlns="http://www.w3.org/2000/09/xmldsig#">
        <X509Data><X509Certificate>MIIBfakecertdata</X509Certificate></X509Data>
      </KeyInfo>
    </KeyDescriptor>
    <SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example/slo"/>
    <SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example/sso"/>
  </IDPSSODescriptor>
</EntityDescriptor>"""


def test_parse_extracts_config() -> None:
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_metadata import parse_idp_metadata_xml

    cfg = parse_idp_metadata_xml(_IDP_METADATA_XML)
    assert cfg["idp_entity_id"] == "https://idp.example/idp"
    assert cfg["idp_sso_url"] == "https://idp.example/sso"
    assert "MIIBfakecertdata" in cfg["idp_x509_cert"]
    assert cfg["idp_slo_url"] == "https://idp.example/slo"


def test_parse_incomplete_raises() -> None:
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_metadata import (
        SamlMetadataError as _Err,
    )
    from dazzle.back.runtime.auth.saml_metadata import (
        parse_idp_metadata_xml,
    )

    # Genuinely incomplete: strip the whole KeyDescriptor so no cert is present (the
    # parser extracts a cert from any KeyDescriptor, so just flipping use= isn't enough).
    start = _IDP_METADATA_XML.index("<KeyDescriptor")
    end = _IDP_METADATA_XML.index("</KeyDescriptor>") + len("</KeyDescriptor>")
    no_cert = _IDP_METADATA_XML[:start] + _IDP_METADATA_XML[end:]
    with pytest.raises(_Err):
        parse_idp_metadata_xml(no_cert)


def test_parse_malformed_raises() -> None:
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_metadata import (
        SamlMetadataError as _Err,
    )
    from dazzle.back.runtime.auth.saml_metadata import (
        parse_idp_metadata_xml,
    )

    with pytest.raises(_Err):
        parse_idp_metadata_xml("not xml at all <<<")
