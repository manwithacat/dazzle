"""In-process SAML IdP test double (#1342) — NOT a test module (no ``test_`` prefix, not
collected). Mints GENUINELY-SIGNED HTTP-Redirect-binding LogoutRequest / LogoutResponse
messages with a throwaway RSA-2048 keypair, so the SP's REAL ``process_slo`` /
``validate_binary_sign`` signature path runs end-to-end with zero real IdP infrastructure.

The signed-query byte format is python3-saml-internal; this double is *verified* against the
real validator (see ``test_idp_double_message_validates_against_real_process_slo``), not
assumed from docs.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

_RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
_NS = (
    'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
    'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id() -> str:
    return "_" + secrets.token_hex(16)


class SamlIdpDouble:
    """An in-process IdP with its own RSA keypair. Put ``idp_cert`` in the SP connection's
    ``idp_x509_cert`` so the SP validates these messages for real."""

    def __init__(self, *, entity_id: str, slo_url: str) -> None:
        from dazzle.back.runtime.auth.saml_sp_keys import generate_sp_keypair

        self.entity_id = entity_id
        self.slo_url = slo_url
        self._key_pem, self._cert_pem = generate_sp_keypair(entity_id)

    @property
    def idp_cert(self) -> str:
        return self._cert_pem

    # ---- message builders ----

    def _logout_request_xml(self, *, name_id: str, sp_sls_url: str) -> str:
        return (
            f'<samlp:LogoutRequest {_NS} ID="{_id()}" Version="2.0" '
            f'IssueInstant="{_now_iso()}" Destination="{sp_sls_url}">'
            f"<saml:Issuer>{self.entity_id}</saml:Issuer>"
            f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
            f"{name_id}</saml:NameID>"
            f"</samlp:LogoutRequest>"
        )

    def _logout_response_xml(self, *, in_response_to: str, sp_sls_url: str) -> str:
        return (
            f'<samlp:LogoutResponse {_NS} ID="{_id()}" Version="2.0" '
            f'IssueInstant="{_now_iso()}" Destination="{sp_sls_url}" '
            f'InResponseTo="{in_response_to}">'
            f"<saml:Issuer>{self.entity_id}</saml:Issuer>"
            f"<samlp:Status><samlp:StatusCode "
            f'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
            f"</samlp:LogoutResponse>"
        )

    def _sign_redirect(self, param: str, xml: str) -> dict[str, str]:
        from onelogin.saml2.utils import OneLogin_Saml2_Utils as U

        deflated = U.deflate_and_base64_encode(xml)
        if isinstance(deflated, bytes):
            deflated = deflated.decode("ascii")
        # Canonical signed query for the HTTP-Redirect binding: <param>=<enc>&SigAlg=<enc>,
        # each value URL-encoded exactly as the validator re-encodes get_data.
        signed_query = f"{param}={quote(deflated, safe='')}&SigAlg={quote(_RSA_SHA256, safe='')}"
        # sign_binary's default algorithm is RSA-SHA256 (an xmlsec Transform, not the URI);
        # we advertise the matching SigAlg URI so the SP reconstructs + validates the same.
        signature = U.sign_binary(signed_query, self._key_pem)
        if isinstance(signature, str):
            signature = signature.encode("ascii")
        return {
            param: deflated,
            "SigAlg": _RSA_SHA256,
            "Signature": base64.b64encode(signature).decode(),
        }

    def signed_logout_request(self, *, name_id: str, sp_sls_url: str) -> dict[str, str]:
        """Redirect-binding query params for an IdP-initiated LogoutRequest."""
        return self._sign_redirect(
            "SAMLRequest", self._logout_request_xml(name_id=name_id, sp_sls_url=sp_sls_url)
        )

    def signed_logout_response(self, *, in_response_to: str, sp_sls_url: str) -> dict[str, str]:
        """Redirect-binding query params for a LogoutResponse (SP-initiated completion)."""
        return self._sign_redirect(
            "SAMLResponse",
            self._logout_response_xml(in_response_to=in_response_to, sp_sls_url=sp_sls_url),
        )


class _SlsUrl:
    def __init__(self, base: str) -> None:
        from urllib.parse import urlparse

        u = urlparse(base.rstrip("/") + "/auth/saml/sls")
        self.scheme = u.scheme
        self.hostname = u.hostname
        self.path = u.path


class FakeSlsRequest:
    """A request object shaped for ``NativeSAMLProvider`` (base_url + url + query_params)."""

    def __init__(self, params: dict[str, str], *, base_url: str = "https://app.test/") -> None:
        self.base_url = base_url
        self.url = _SlsUrl(base_url)
        self.query_params: dict[str, Any] = dict(params)
