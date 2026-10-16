"""Live reachability probe for an enterprise connection (#1342 — `doctor --probe`).

OPT-IN, CLI-ONLY network I/O layered on top of the network-free ``connection_doctor``
audit. The org-admin web readiness panel deliberately does **not** use this — network I/O
on a request path is an SSRF surface, and ``connection_doctor`` stays pure precisely so the
panel can reuse it. The SSRF gate is local to this module: https-only, public-IP-only (every
resolved address must be globally routable), no userinfo, no redirects, size-capped.

What gets probed:
- **OIDC** — the discovery document (``discovery_url`` or ``{issuer}/.well-known/openid-configuration``):
  fetched + validated as JSON carrying ``authorization_endpoint`` and ``token_endpoint``.
- **SCIM** — inbound (the IdP pushes to us): no outbound endpoint to probe.

All probe checks are ``recommended`` — a transient IdP outage must not flip the activation-ready
gate, which is about *config* completeness. Reachability is supplementary live evidence.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from dazzle.http.runtime.auth.connection_doctor import Check
from dazzle.http.runtime.tenant.aliases import AliasError

_MAX_PROBE_BYTES = 1_048_576  # 1 MiB — discovery docs are tiny; this only guards memory
_PROBE_TIMEOUT = 10.0

#: Injectable transport: ``url -> (status_code, body)``. Default is the SSRF-guarded fetch.
HttpGet = Callable[[str], "tuple[int, bytes]"]


class ProbeError(AliasError):
    """A probe could not reach/validate an endpoint. ``reason`` is a stable code
    (an SSRF-reject code from ``validate_probe_url``, or ``unreachable``). Shares
    ``AliasError``'s ``(reason, message)`` shape, like ``DomainVerificationError``."""


def validate_probe_url(url: str) -> None:
    """Raise ``ProbeError`` unless ``url`` is an https URL whose host resolves only to
    globally-routable public IPs (anti-SSRF).

    Allowlist-by-exclusion (``not ip.is_global``) also rejects ranges ``is_private`` misses
    (RFC 6598 CGNAT, reserved space). IPv4-mapped IPv6 is unwrapped first. Userinfo and
    backslash URL forms are refused (urlparse and httpx can disagree on the real host).

    SSRF-RESIDUAL: this validates the resolution *now*; httpx re-resolves at connect time,
    so a DNS-rebinding window exists. Accepted: the caller is the operator CLI on a trusted
    resolver, never a request path.
    """
    if "\\" in url:
        raise ProbeError("userinfo", "probe URL must not contain a backslash")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ProbeError("scheme", "probe URL must be https")
    if parsed.username is not None or parsed.password is not None:
        raise ProbeError("userinfo", "probe URL must not contain userinfo")
    host = parsed.hostname or ""
    if not host:
        raise ProbeError("host", "probe URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ProbeError("dns", f"cannot resolve {host!r}") from exc
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])  # drop any IPv6 scope id
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if not ip.is_global:
            raise ProbeError("private_ip", f"{host!r} resolves to a non-public address ({ip})")


def _default_http_get(url: str) -> tuple[int, bytes]:
    """SSRF-guarded GET → ``(status_code, body)``.

    Runs :func:`validate_probe_url` for the SSRF gate, then streams with no
    redirects (a redirect could bounce to an internal host), ``Accept-Encoding: identity``
    (so the bytes we cap are the bytes we read), and a 1 MiB size cap. Deliberately does NOT
    ``raise_for_status`` — the caller decides what a status means (reachability vs content).
    Connect/DNS errors and SSRF rejects surface as ``ProbeError``.
    """
    validate_probe_url(url)

    chunks: list[bytes] = []
    total = 0
    try:
        with httpx.stream(  # DZ-HTTP-NORETRY  one-shot capped probe stream
            "GET",
            url,
            timeout=_PROBE_TIMEOUT,
            follow_redirects=False,
            headers={"Accept-Encoding": "identity"},
        ) as resp:
            status = resp.status_code
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > _MAX_PROBE_BYTES:
                    break  # only the head of the doc is needed; the cap defends memory
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ProbeError("unreachable", str(exc)) from exc
    return status, b"".join(chunks)


def _recommended(name: str, ok: bool, ok_detail: str, warn_detail: str) -> Check:
    return Check(
        name=name,
        level="recommended",
        status="ok" if ok else "warn",
        detail=ok_detail if ok else warn_detail,
    )


def _probe_oidc(config: dict[str, Any], http_get: HttpGet) -> list[Check]:
    # config is loaded from a JSONB column, so coerce to str — a non-string issuer/discovery_url
    # must not crash the "never raises" contract (e.g. `.rstrip` on a list).
    issuer = str(config.get("issuer") or "").rstrip("/")
    url = str(config.get("discovery_url") or "") or (
        f"{issuer}/.well-known/openid-configuration" if issuer else ""
    )
    if not url:
        return [_recommended("discovery_reachable", False, "", "no issuer/discovery_url to probe")]
    try:
        status, body = http_get(url)
    except ProbeError as exc:
        return [
            _recommended("discovery_reachable", False, "", f"unreachable ({exc.reason}): {exc}")
        ]
    if status != 200:
        return [_recommended("discovery_reachable", False, "", f"discovery returned HTTP {status}")]
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return [_recommended("discovery_valid", False, "", "discovery is not valid JSON")]
    if not isinstance(doc, dict):
        # a malicious/misconfigured IdP could serve valid JSON that isn't an object (e.g. `[]`)
        return [_recommended("discovery_valid", False, "", "discovery JSON is not an object")]
    missing = [k for k in ("authorization_endpoint", "token_endpoint") if not doc.get(k)]
    if missing:
        return [_recommended("discovery_valid", False, "", f"discovery JSON missing {missing}")]
    return [_recommended("discovery_reachable", True, f"discovery reachable + valid ({url})", "")]


def probe_connection(
    connection: Any, *, http_get: HttpGet = _default_http_get
) -> tuple[Check, ...]:
    """Live-reachability probe for ``connection`` → recommended-level ``Check`` records.

    ``http_get`` is injectable so tests need no network. Touches only non-secret config URLs —
    never a secret. Never raises: a transport/SSRF failure becomes a ``warn`` check.
    """
    config = connection.config or {}
    conn_type = connection.type
    if conn_type == "oidc":
        return tuple(_probe_oidc(config, http_get))
    if conn_type == "scim":
        return (
            Check(
                name="scim_inbound",
                level="recommended",
                status="ok",
                detail="SCIM is inbound (the IdP pushes to us) — no outbound endpoint to probe",
            ),
        )
    return (
        Check(
            name="probe",
            level="recommended",
            status="warn",
            detail=f"no live probe defined for connection type {conn_type!r}",
        ),
    )
