"""SAML IdP-metadata import (auth Plan 5 — #1342 SAML cluster).

Turns an IdP's published SAML metadata (a URL or a local file) into the connection
config keys `create-saml` would otherwise be hand-fed. The URL fetch is SSRF-guarded
(https-only, public-IP-only, no redirects, bounded + size-capped); the XML parse is
delegated to python3-saml (Dazzle never hand-rolls XML — XXE safety / ADR).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_MAX_METADATA_BYTES = 1_048_576  # 1 MiB cap on a fetched metadata document


class SamlMetadataError(RuntimeError):
    """IdP metadata can't be fetched/parsed. ``reason`` is a stable code
    (scheme / userinfo / host / dns / private_ip / fetch / too_large / parse /
    incomplete / no_saml_extra)."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def validate_metadata_url(url: str) -> None:
    """Raise ``SamlMetadataError`` unless ``url`` is an https URL whose host resolves only
    to globally-routable public IPs (anti-SSRF).

    Uses allowlist-by-exclusion (``not ip.is_global``) rather than enumerating private
    ranges — this also rejects the ranges ``is_private`` misses (RFC 6598 CGNAT
    100.64.0.0/10, future-reserved space, etc.). IPv4-mapped IPv6 (``::ffff:a.b.c.d``) is
    unwrapped first so a mapped loopback/link-local can't slip past. Userinfo/backslash
    URL forms are refused outright (urlparse and httpx can disagree on the real host —
    the CVE-2023-24329 split class).

    SSRF-RESIDUAL: this validates the resolution *now*; httpx re-resolves at connect time,
    so a DNS-rebinding window exists. Two callers, both accepted:
    - the operator CLI (`create-saml --idp-metadata-url`) — trusted resolver;
    - the in-app org-admin create surface (`POST /auth/connections/create`, #1342) — an
      authenticated, RBAC-gated, privileged caller; the fetch is https-only, public-IP-only,
      redirect-free, and time/size-capped. This is a deliberate, accepted request-path exposure.
    If the exposure ever widens to a less-privileged caller, pin the resolved IP (resolve once,
    connect to that IP with the original Host header + SNI) to close the rebinding window.
    """
    if "\\" in url:
        raise SamlMetadataError("userinfo", "IdP metadata URL must not contain a backslash")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise SamlMetadataError("scheme", "IdP metadata URL must be https")
    if parsed.username is not None or parsed.password is not None:
        raise SamlMetadataError("userinfo", "IdP metadata URL must not contain userinfo")
    host = parsed.hostname or ""
    if not host:
        raise SamlMetadataError("host", "IdP metadata URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SamlMetadataError("dns", f"cannot resolve {host!r}") from exc
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])  # drop any IPv6 scope id
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if not ip.is_global:
            raise SamlMetadataError(
                "private_ip", f"{host!r} resolves to a non-public address ({ip})"
            )


def fetch_idp_metadata(url: str, *, timeout: float = 10.0) -> str:
    """Fetch IdP metadata XML from a validated https URL. No redirects (a redirect could
    bounce to an internal host), bounded timeout, and a STREAMING size cap so a
    compression-amplified ("zip bomb") body can't blow memory before the check. Returns
    the XML text."""
    validate_metadata_url(url)
    import httpx

    chunks: list[bytes] = []
    total = 0
    try:
        with httpx.stream(  # DZ-HTTP-NORETRY  one-shot capped metadata stream
            "GET",
            url,
            timeout=timeout,
            follow_redirects=False,
            # Disable transparent decompression so the wire bytes we cap are the bytes we
            # decode (defence-in-depth against decompression amplification).
            headers={"Accept-Encoding": "identity"},
        ) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > _MAX_METADATA_BYTES:
                    raise SamlMetadataError("too_large", "IdP metadata exceeds the 1 MiB cap")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise SamlMetadataError("fetch", f"could not fetch IdP metadata: {exc}") from exc
    return b"".join(chunks).decode("utf-8", errors="replace")


def parse_idp_metadata_xml(xml: str) -> dict[str, str]:
    """Extract SAML connection config from IdP metadata XML →
    {idp_entity_id, idp_sso_url, idp_x509_cert, [idp_slo_url]}. Raises ``SamlMetadataError``
    when a required value is absent. XML parsing is delegated to python3-saml's
    OneLogin_Saml2_IdPMetadataParser (no hand-rolled XML — XXE safety)."""
    try:
        from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
    except ImportError as exc:
        raise SamlMetadataError(
            "no_saml_extra", "parsing IdP metadata needs the [saml] extra"
        ) from exc
    try:
        data = OneLogin_Saml2_IdPMetadataParser.parse(xml)
    except Exception as exc:  # noqa: BLE001 — normalise lxml/onelogin errors to one typed error
        raise SamlMetadataError("parse", f"could not parse IdP metadata: {exc}") from exc
    idp = (data or {}).get("idp") or {}
    entity_id = idp.get("entityId") or ""
    sso_url = (idp.get("singleSignOnService") or {}).get("url") or ""
    cert = idp.get("x509cert") or ""
    missing = [
        n for n, v in (("entityId", entity_id), ("ssoUrl", sso_url), ("x509cert", cert)) if not v
    ]
    if missing:
        raise SamlMetadataError("incomplete", f"IdP metadata is missing {missing}")
    out = {"idp_entity_id": entity_id, "idp_sso_url": sso_url, "idp_x509_cert": cert}
    slo = (idp.get("singleLogoutService") or {}).get("url")
    if slo:
        out["idp_slo_url"] = slo
    return out
