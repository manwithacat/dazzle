# SAML IdP-metadata auto-import (Feature D) — Design

**Issue:** #1342 (enterprise auth) — SAML cluster, feature 1 of 4.
**Date:** 2026-06-07
**Status:** Approved (design), pending spec review.

## Problem

`dazzle auth connection create-saml` requires the operator to hand-transcribe the IdP's
`entity_id`, SSO URL, and X.509 signing cert from the IdP admin console (three flags, one a
PEM file). Every SAML IdP publishes a standard **metadata XML** carrying exactly those values.
Auto-importing it removes the most error-prone hand-config step and directly serves the
agent-driven north-star: an agent (or operator) points create-saml at the IdP metadata
(URL or file) and Dazzle fills the connection config.

This is feature 1 of the SAML cluster (independent; no SP keypair). The other three
(SP-signed AuthnRequests, encrypted assertions, SLO) follow in their own cycles.

## Scope

- **In:** parse an IdP metadata document (URL fetch or local file) into the existing SAML
  connection config keys; an SSRF-guarded fetch; CLI flags on `create-saml`.
- **Out:** no new runtime route, RBAC, or capability change (create-saml is operator CLI).
  No SP keypair. No metadata *signature* validation of the IdP metadata itself (the IdP cert
  it carries is the trust anchor used at assertion time; metadata signing is a separate
  concern and most operators fetch over HTTPS from a trusted console — noted as a follow-up).
  No background re-fetch / metadata refresh (one-shot at create time).

## Architecture

A new `onelogin`-free-where-possible module does the fetch + guard + parse; the CLI merges the
parsed values with any explicit flags and stores the same `config` keys it does today.

### New module `src/dazzle/back/runtime/auth/saml_metadata.py`

```python
class SamlMetadataError(RuntimeError):
    """IdP metadata can't be fetched/parsed. ``reason`` is a stable code."""
    def __init__(self, reason: str, message: str = "") -> None: ...

# --- pure SSRF guard (no onelogin; fully locally testable) ---
def validate_metadata_url(url: str) -> None:
    """Raise SamlMetadataError unless `url` is an https URL whose host resolves only to
    public IPs. Blocks private/loopback/link-local/reserved/multicast (anti-SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise SamlMetadataError("scheme", "IdP metadata URL must be https")
    host = parsed.hostname or ""
    if not host:
        raise SamlMetadataError("host", "IdP metadata URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SamlMetadataError("dns", f"cannot resolve {host!r}") from exc
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise SamlMetadataError("private_ip", f"{host!r} resolves to a non-public address")

# --- guarded fetch (httpx; no onelogin) ---
_MAX_METADATA_BYTES = 1_048_576  # 1 MiB cap

def fetch_idp_metadata(url: str, *, timeout: float = 10.0) -> str:
    """Fetch IdP metadata XML over a validated https URL. No redirects (a redirect could
    bounce to an internal host), bounded timeout, size-capped. Returns the XML text."""
    validate_metadata_url(url)
    import httpx
    resp = httpx.get(url, timeout=timeout, follow_redirects=False)
    resp.raise_for_status()
    if len(resp.content) > _MAX_METADATA_BYTES:
        raise SamlMetadataError("too_large", "IdP metadata exceeds the 1 MiB cap")
    return resp.text

# --- parse (lazy onelogin import; XML/XXE delegated to python3-saml) ---
def parse_idp_metadata_xml(xml: str) -> dict[str, str]:
    """Extract the SAML connection config from IdP metadata XML. Returns
    {idp_entity_id, idp_sso_url, idp_x509_cert, [idp_slo_url]}. Raises SamlMetadataError
    when a required value is absent. XML parsing is delegated to python3-saml's
    OneLogin_Saml2_IdPMetadataParser (Dazzle never hand-rolls XML — ADR / XXE safety)."""
    try:
        from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
    except ImportError as exc:
        raise SamlMetadataError("no_saml_extra", "the [saml] extra is required") from exc
    try:
        data = OneLogin_Saml2_IdPMetadataParser.parse(xml)
    except Exception as exc:  # parser raises various lxml/onelogin errors on bad XML
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
        out["idp_slo_url"] = slo  # forward-sets SLO (feature A) at no cost
    return out
```

(The broad `except Exception` around the parser is justified — python3-saml raises a variety
of lxml/onelogin exceptions on malformed XML; we normalise them to one `SamlMetadataError`.
It is NOT a bare `except: pass` — it re-raises a typed error with the cause, so the
`test_no_bare_except_pass` gate is satisfied.)

### CLI change — `create-saml` (`src/dazzle/cli/auth_connection.py`)

- Add `--idp-metadata-url` and `--idp-metadata-file` options (both default `""`).
- Make the three existing flags optional (default `""`): `--idp-entity-id`, `--idp-sso-url`,
  `--idp-cert-file`.
- Logic:
  1. `--idp-metadata-url` and `--idp-metadata-file` are mutually exclusive → error if both.
  2. If a metadata source is given, obtain XML (`fetch_idp_metadata(url)` or
     `Path(file).read_text()`), then `parse_idp_metadata_xml(xml)` → `parsed` dict. Any
     `SamlMetadataError` → a clean `console.print` + `Exit(1)` (no traceback).
  3. Merge with explicit-override: `entity_id = idp_entity_id or parsed.get("idp_entity_id","")`,
     same for sso_url; cert from `--idp-cert-file` (read PEM) else `parsed.get("idp_x509_cert","")`.
  4. If any of the three is still empty → error listing what's missing and pointing at
     `--idp-metadata-url/--idp-metadata-file` or the explicit flags.
  5. Build the same `config` dict as today (adding `idp_slo_url` when parsed), create the
     connection unchanged.

## Files

| File | Change |
|------|--------|
| `src/dazzle/back/runtime/auth/saml_metadata.py` | NEW — `validate_metadata_url`, `fetch_idp_metadata`, `parse_idp_metadata_xml`, `SamlMetadataError` |
| `src/dazzle/cli/auth_connection.py` | `create-saml`: metadata flags, optional idp flags, merge + validate |
| `tests/unit/test_saml_metadata.py` | NEW — URL validator (local) + parse/CLI (importorskip onelogin) |
| `tests/unit/test_auth_connection_cli.py` | `create-saml` metadata-file path + missing-args error |
| `docs/reference/enterprise-sso.md` | flip the conformance-matrix row; create-saml setup note |
| `CHANGELOG.md` | Added entry + Agent Guidance; `/bump patch` → v0.81.80 |

## Testing

- **Local (no onelogin):**
  - `validate_metadata_url`: rejects `http://…` (`scheme`); rejects a host that resolves to a
    private IP (monkeypatch `socket.getaddrinfo` → `127.0.0.1`/`10.x`) (`private_ip`); passes a
    public IP (monkeypatch → `93.184.216.34`); rejects unresolvable (`dns`).
  - `fetch_idp_metadata`: monkeypatch `httpx.get` → a fake response; assert size cap raises
    `too_large`; assert `follow_redirects=False` is passed; assert the validator runs first
    (a non-https URL never reaches httpx).
  - CLI `create-saml` with neither metadata nor the full triple → `Exit(1)` with a "need
    metadata or …" message (no parse, so no onelogin needed).
  - CLI `create-saml` with both `--idp-metadata-url` and `--idp-metadata-file` → error.
- **CI (`[saml]` extra; `pytest.importorskip("onelogin")`):**
  - `parse_idp_metadata_xml` on a minimal valid IdP `EntityDescriptor`/`IDPSSODescriptor`
    fixture → extracts entity_id/sso_url/cert; includes `idp_slo_url` when an SLS is present;
    raises `incomplete` when the cert/SSO is missing; raises `parse` on malformed XML.
  - CLI `create-saml --idp-metadata-file <fixture>` → `store.created["config"]` carries the
    parsed entity_id/sso_url/cert; an explicit `--idp-entity-id` overrides the parsed one.

The minimal IdP-metadata fixture is a small inline XML string (one `EntityDescriptor` with an
`IDPSSODescriptor`, a `KeyDescriptor use="signing"` cert, and a Redirect `SingleSignOnService`).

## Docs

`docs/reference/enterprise-sso.md`: change the SAML conformance-matrix row **"IdP metadata
auto-import | ❌ | Provide entity id / SSO URL / cert explicitly"** to **✅** with a note, and
add to the create-saml setup line that `--idp-metadata-url`/`--idp-metadata-file` auto-fills
the three IdP values (HTTPS-only fetch, SSRF-guarded). CHANGELOG `Added` + an Agent Guidance
bullet (an agent can create a SAML connection from an IdP metadata URL/file; the fetch is
https-only + private-IP-blocked; XML parsing stays delegated to python3-saml).

## Execution

Security-relevant (network fetch + XML). Hybrid: implement inline, then an independent review
focused on (a) the **SSRF guard** — scheme allowlist, private/loopback/link-local/reserved IP
rejection, `follow_redirects=False`, timeout, size cap, and that the validator runs *before*
any network call; and (b) confirming **XML parsing is fully delegated** to python3-saml (no
hand-rolled `lxml`/`ElementTree` parse that could reintroduce XXE). Run the non-e2e suite (the
local tests; the onelogin tests skip locally + run in CI).

## Failure-mode notes (per CLAUDE.md review rule)

- **Modes risked:** SSRF (operator-supplied URL → internal request) and XXE (parsing
  attacker-influenced XML).
- **Detectors:** the validator unit tests (scheme + private-IP + redirect + size); XXE is
  structurally avoided by delegating to python3-saml (no hand-rolled XML parser introduced).
- **Live:** the validator tests run in the normal non-e2e suite; the parser tests in CI's
  `[saml]` job.
- **Traceable:** a created connection's `config` shows exactly the imported values; the import
  source is an explicit operator flag.
- **Semantics preserved:** the stored `config` keys are unchanged — the IdP cert remains the
  assertion-time trust anchor; auto-import only changes how those values are *entered*.
