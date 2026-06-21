"""Live reachability probe for an enterprise connection (#1342 — `doctor --probe`).

OPT-IN, CLI-ONLY network I/O layered on top of the network-free ``connection_doctor``
audit. The org-admin web readiness panel deliberately does **not** use this — network I/O
on a request path is an SSRF surface, and ``connection_doctor`` stays pure precisely so the
panel can reuse it. The SSRF gate is **reused** from ``saml_metadata.validate_metadata_url``
(https-only, public-IP-only, no redirects, size-capped) rather than reinvented.

What gets probed:
- **OIDC** — the discovery document (``discovery_url`` or ``{issuer}/.well-known/openid-configuration``):
  fetched + validated as JSON carrying ``authorization_endpoint`` and ``token_endpoint``.
- **SAML** — ``idp_sso_url`` (+ ``idp_slo_url`` when present) for *reachability*: any HTTP status
  means the endpoint is serving (an SSO endpoint with no SAMLRequest legitimately returns 200/400/405);
  only DNS/connect/timeout/SSRF-reject is a failure. ``idp_metadata_url`` is not persisted, so there is
  nothing to re-fetch.
- **SCIM** — inbound (the IdP pushes to us): no outbound endpoint to probe.

All probe checks are ``recommended`` — a transient IdP outage must not flip the activation-ready
gate, which is about *config* completeness. Reachability is supplementary live evidence.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from dazzle.http.runtime.auth.connection_doctor import Check

_MAX_PROBE_BYTES = 1_048_576  # 1 MiB — discovery docs are tiny; this only guards memory
_PROBE_TIMEOUT = 10.0

#: Injectable transport: ``url -> (status_code, body)``. Default is the SSRF-guarded fetch.
HttpGet = Callable[[str], "tuple[int, bytes]"]


class ProbeError(RuntimeError):
    """A probe could not reach/validate an endpoint. ``reason`` is a stable code
    (an SSRF-reject code from ``validate_metadata_url``, or ``unreachable``)."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def _default_http_get(url: str) -> tuple[int, bytes]:
    """SSRF-guarded GET → ``(status_code, body)``.

    Reuses ``saml_metadata.validate_metadata_url`` for the SSRF gate, then streams with no
    redirects (a redirect could bounce to an internal host), ``Accept-Encoding: identity``
    (so the bytes we cap are the bytes we read), and a 1 MiB size cap. Deliberately does NOT
    ``raise_for_status`` — the caller decides what a status means (reachability vs content).
    Connect/DNS errors and SSRF rejects surface as ``ProbeError``.
    """
    from dazzle.http.runtime.auth.saml_metadata import SamlMetadataError, validate_metadata_url

    try:
        validate_metadata_url(url)
    except SamlMetadataError as exc:
        raise ProbeError(exc.reason, str(exc)) from exc

    import httpx

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


def _reachability_check(name: str, url: str, http_get: HttpGet) -> Check:
    """Any HTTP response means the endpoint is serving; only a transport/SSRF error is a fail."""
    try:
        status, _ = http_get(url)
    except ProbeError as exc:
        return _recommended(name, False, "", f"unreachable ({exc.reason}): {exc}")
    return _recommended(name, True, f"reachable (HTTP {status})", "")


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


def _probe_saml(config: dict[str, Any], http_get: HttpGet) -> list[Check]:
    # str-coerce (JSONB config) so a non-string url can't escape the "never raises" contract.
    checks: list[Check] = []
    sso = str(config.get("idp_sso_url") or "")
    if not sso:
        checks.append(_recommended("idp_sso_reachable", False, "", "no idp_sso_url to probe"))
    else:
        checks.append(_reachability_check("idp_sso_reachable", sso, http_get))
    slo = str(config.get("idp_slo_url") or "")
    if slo:
        checks.append(_reachability_check("idp_slo_reachable", slo, http_get))
    return checks


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
    if conn_type == "saml":
        return tuple(_probe_saml(config, http_get))
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
