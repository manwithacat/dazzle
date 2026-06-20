# SAML IdP-metadata auto-import (Feature D) — Implementation Plan

> **For agentic workers:** execute task-by-task. Steps use checkbox (`- [ ]`) syntax.
> Spec: `docs/superpowers/specs/2026-06-07-saml-idp-metadata-import-design.md`.

**Goal:** `create-saml --idp-metadata-url/--idp-metadata-file` auto-fills the IdP config
(`idp_entity_id` / `idp_sso_url` / `idp_x509_cert`, + `idp_slo_url` if present) from IdP
metadata, via an SSRF-guarded fetch and python3-saml's metadata parser.

**Architecture:** New `saml_metadata.py` (onelogin-free URL guard + httpx fetch; lazy-onelogin
parse). `create-saml` gains the two metadata flags, makes the three idp flags optional, and
merges parsed values with explicit overrides. No new route/RBAC/capability.

**Tech Stack:** Python 3.12, httpx (core dep), python3-saml (`[saml]` extra — CI only),
Typer CLI, pytest (`importorskip("onelogin")` for parser tests).

**Execution mode:** Hybrid (inline) per global CLAUDE.md — implement inline, then an
independent review focused on the SSRF guard + XML-parse delegation.

---

### Task 1: `saml_metadata.py` — SSRF-guarded URL validation + fetch

**Files:**
- Create: `src/dazzle/http/runtime/auth/saml_metadata.py`
- Test: `tests/unit/test_saml_metadata.py`

- [ ] **Step 1: Write the failing tests (local — no onelogin)**

```python
# tests/unit/test_saml_metadata.py
"""SAML IdP-metadata import: SSRF guard + fetch (local) + parse (CI: onelogin)."""

import socket

import pytest

from dazzle.http.runtime.auth.saml_metadata import (
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


def test_fetch_size_capped(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))

    class _Resp:
        content = b"x" * (1_048_576 + 1)
        text = "x"

        def raise_for_status(self):
            return None

    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    with pytest.raises(SamlMetadataError) as ei:
        fetch_idp_metadata("https://idp.example/metadata")
    assert ei.value.reason == "too_large"


def test_fetch_passes_no_redirects(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    seen = {}

    class _Resp:
        content = b"<xml/>"
        text = "<xml/>"

        def raise_for_status(self):
            return None

    import httpx

    def _get(url, **kw):
        seen.update(kw)
        return _Resp()

    monkeypatch.setattr(httpx, "get", _get)
    assert fetch_idp_metadata("https://idp.example/metadata") == "<xml/>"
    assert seen["follow_redirects"] is False


def test_fetch_rejects_http_before_network(monkeypatch) -> None:
    # The validator must run before any httpx call.
    import httpx

    def _boom(*a, **k):
        raise AssertionError("httpx.get must not be called for a non-https URL")

    monkeypatch.setattr(httpx, "get", _boom)
    with pytest.raises(SamlMetadataError):
        fetch_idp_metadata("http://idp.example/metadata")
```

- [ ] **Step 2: Run — expect FAIL** (module missing).
Run: `pytest tests/unit/test_saml_metadata.py -q -k "validate or fetch"`

- [ ] **Step 3: Implement the module** (the `validate_metadata_url` / `fetch_idp_metadata` /
`parse_idp_metadata_xml` / `SamlMetadataError` bodies from the spec). Full file:

```python
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
    (scheme / host / dns / private_ip / too_large / parse / incomplete / no_saml_extra)."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def validate_metadata_url(url: str) -> None:
    """Raise ``SamlMetadataError`` unless ``url`` is an https URL whose host resolves only
    to public IPs (anti-SSRF: blocks private/loopback/link-local/reserved/multicast)."""
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
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise SamlMetadataError(
                "private_ip", f"{host!r} resolves to a non-public address ({ip})"
            )


def fetch_idp_metadata(url: str, *, timeout: float = 10.0) -> str:
    """Fetch IdP metadata XML from a validated https URL. No redirects (a redirect could
    bounce to an internal host), bounded timeout, size-capped. Returns the XML text."""
    validate_metadata_url(url)
    import httpx

    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=False)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SamlMetadataError("fetch", f"could not fetch IdP metadata: {exc}") from exc
    if len(resp.content) > _MAX_METADATA_BYTES:
        raise SamlMetadataError("too_large", "IdP metadata exceeds the 1 MiB cap")
    return resp.text


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
```

- [ ] **Step 4: Run — expect PASS** (the local validate/fetch tests).
Run: `pytest tests/unit/test_saml_metadata.py -q -k "validate or fetch"`

- [ ] **Step 5: Commit** — `feat(auth): SSRF-guarded SAML IdP-metadata fetch + parse (#1342)`

---

### Task 2: Parser tests (CI — onelogin)

**Files:** `tests/unit/test_saml_metadata.py`

- [ ] **Step 1: Add the onelogin-guarded parser tests** (append):

```python
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
    from dazzle.http.runtime.auth.saml_metadata import parse_idp_metadata_xml

    cfg = parse_idp_metadata_xml(_IDP_METADATA_XML)
    assert cfg["idp_entity_id"] == "https://idp.example/idp"
    assert cfg["idp_sso_url"] == "https://idp.example/sso"
    assert "MIIBfakecertdata" in cfg["idp_x509_cert"]
    assert cfg["idp_slo_url"] == "https://idp.example/slo"


def test_parse_incomplete_raises() -> None:
    pytest.importorskip("onelogin")
    from dazzle.http.runtime.auth.saml_metadata import (
        SamlMetadataError,
        parse_idp_metadata_xml,
    )

    no_cert = _IDP_METADATA_XML.replace(
        "<KeyDescriptor use=\"signing\">", "<KeyDescriptor use=\"encryption\">"
    )
    with pytest.raises(SamlMetadataError):
        parse_idp_metadata_xml(no_cert)


def test_parse_malformed_raises() -> None:
    pytest.importorskip("onelogin")
    from dazzle.http.runtime.auth.saml_metadata import (
        SamlMetadataError,
        parse_idp_metadata_xml,
    )

    with pytest.raises(SamlMetadataError):
        parse_idp_metadata_xml("not xml at all <<<")
```

(If the onelogin parser keys differ slightly at runtime — e.g. the signing cert lands under a
list — adjust `parse_idp_metadata_xml`'s extraction in Task 1 to match; the CI run is the
source of truth since onelogin isn't importable locally. Keep the extraction minimal.)

- [ ] **Step 2: Run** (skips locally; runs in CI).
Run: `pytest tests/unit/test_saml_metadata.py -q`
Expected locally: the parse tests SKIP (no onelogin); the validate/fetch tests PASS.

- [ ] **Step 3: Commit** — `test(auth): SAML IdP-metadata parser tests (CI onelogin) (#1342)`

---

### Task 3: `create-saml` CLI — metadata flags + merge

**Files:**
- Modify: `src/dazzle/cli/auth_connection.py` (`create_saml`)
- Test: `tests/unit/test_auth_connection_cli.py`

- [ ] **Step 1: Write failing CLI tests** (append to test_auth_connection_cli.py).
The fake `_Store.create_connection` already records `self.created = kw`.

```python
# ---- create-saml metadata import (#1342) ----


def test_create_saml_requires_metadata_or_flags(monkeypatch) -> None:
    _patch_store(monkeypatch, _Store())
    r = runner.invoke(auth_app, ["connection", "create-saml", "--tenant", "org-1"])
    assert r.exit_code == 1 and "metadata" in r.output.lower()


def test_create_saml_metadata_url_and_file_mutually_exclusive(monkeypatch, tmp_path) -> None:
    _patch_store(monkeypatch, _Store())
    f = tmp_path / "idp.xml"
    f.write_text("<xml/>")
    r = runner.invoke(
        auth_app,
        [
            "connection", "create-saml", "--tenant", "org-1",
            "--idp-metadata-url", "https://idp/x", "--idp-metadata-file", str(f),
        ],
    )
    assert r.exit_code == 1 and "exclusive" in r.output.lower()


def test_create_saml_metadata_file_fills_config(monkeypatch, tmp_path) -> None:
    pytest.importorskip("onelogin")
    store = _Store()
    _patch_store(monkeypatch, store)
    f = tmp_path / "idp.xml"
    f.write_text(_SAML_IDP_METADATA)  # module-level fixture string (same as test_saml_metadata)
    r = runner.invoke(
        auth_app,
        ["connection", "create-saml", "--tenant", "org-1", "--idp-metadata-file", str(f)],
    )
    assert r.exit_code == 0
    cfg = store.created["config"]
    assert cfg["idp_entity_id"] == "https://idp.example/idp"
    assert cfg["idp_sso_url"] == "https://idp.example/sso"
    assert "MIIBfakecertdata" in cfg["idp_x509_cert"]


def test_create_saml_explicit_flag_overrides_metadata(monkeypatch, tmp_path) -> None:
    pytest.importorskip("onelogin")
    store = _Store()
    _patch_store(monkeypatch, store)
    f = tmp_path / "idp.xml"
    f.write_text(_SAML_IDP_METADATA)
    r = runner.invoke(
        auth_app,
        [
            "connection", "create-saml", "--tenant", "org-1",
            "--idp-metadata-file", str(f), "--idp-entity-id", "https://override/idp",
        ],
    )
    assert r.exit_code == 0
    assert store.created["config"]["idp_entity_id"] == "https://override/idp"
```

Add the `_SAML_IDP_METADATA` fixture string at the top of the test file (copy of the one in
test_saml_metadata.py). `pytest` is already imported there.

- [ ] **Step 2: Run — expect FAIL** (flags don't exist).
Run: `pytest tests/unit/test_auth_connection_cli.py -q -k create_saml`

- [ ] **Step 3: Rewrite `create_saml`.** Make the three idp flags optional, add the two
metadata flags, and merge. Replace the signature + the cert-read/config-build block:

```python
@connection_app.command("create-saml")
def create_saml(
    tenant: Annotated[str, typer.Option("--tenant", help="Organization (tenant) id")],
    idp_entity_id: Annotated[
        str, typer.Option("--idp-entity-id", help="IdP entity id (issuer); from metadata if omitted")
    ] = "",
    idp_sso_url: Annotated[
        str, typer.Option("--idp-sso-url", help="IdP SSO redirect URL; from metadata if omitted")
    ] = "",
    idp_cert_file: Annotated[
        str,
        typer.Option("--idp-cert-file", help="IdP X.509 signing cert (PEM); from metadata if omitted"),
    ] = "",
    idp_metadata_url: Annotated[
        str,
        typer.Option("--idp-metadata-url", help="Fetch IdP metadata from this https URL (auto-fill)"),
    ] = "",
    idp_metadata_file: Annotated[
        str,
        typer.Option("--idp-metadata-file", help="Read IdP metadata from this local file (auto-fill)"),
    ] = "",
    email_attribute: Annotated[
        str, typer.Option("--email-attribute", help="SAML attr holding email (else NameID)")
    ] = "",
    groups_attribute: Annotated[
        str, typer.Option("--groups-attribute", help="SAML attr holding groups (default 'groups')")
    ] = "",
    group_map: Annotated[
        list[str] | None,
        typer.Option("--group-map", help="IdP group→role, e.g. --group-map eng=engineer"),
    ] = None,
) -> None:
    """Create a SAML connection from the IdP's metadata (entity id, SSO URL, signing cert).

    Provide the three values explicitly, or auto-fill them from the IdP's metadata with
    --idp-metadata-url (https, SSRF-guarded fetch) or --idp-metadata-file (local). Explicit
    flags override metadata. The IdP signing cert is PUBLIC (config, not secrets).
    """
    from pathlib import Path

    from dazzle.http.runtime.auth.saml_metadata import (
        SamlMetadataError,
        fetch_idp_metadata,
        parse_idp_metadata_xml,
    )

    if idp_metadata_url and idp_metadata_file:
        console.print("[red]--idp-metadata-url and --idp-metadata-file are mutually exclusive[/red]")
        raise typer.Exit(code=1)

    parsed: dict[str, str] = {}
    if idp_metadata_url or idp_metadata_file:
        try:
            if idp_metadata_url:
                xml = fetch_idp_metadata(idp_metadata_url)
            else:
                xml = Path(idp_metadata_file).read_text(encoding="utf-8")
            parsed = parse_idp_metadata_xml(xml)
        except SamlMetadataError as exc:
            console.print(f"[red]IdP metadata import failed ({exc.reason}): {exc}[/red]")
            raise typer.Exit(code=1) from exc
        except OSError as exc:
            console.print(f"[red]Cannot read --idp-metadata-file {idp_metadata_file!r}: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    cert = ""
    if idp_cert_file:
        try:
            cert = Path(idp_cert_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            console.print(f"[red]Cannot read --idp-cert-file {idp_cert_file!r}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
    # Explicit flags override metadata.
    entity_id = idp_entity_id or parsed.get("idp_entity_id", "")
    sso_url = idp_sso_url or parsed.get("idp_sso_url", "")
    cert = cert or parsed.get("idp_x509_cert", "")

    missing = [
        n for n, v in (("entity id", entity_id), ("SSO URL", sso_url), ("signing cert", cert)) if not v
    ]
    if missing:
        console.print(
            f"[red]Missing IdP {', '.join(missing)}. Provide --idp-metadata-url/"
            "--idp-metadata-file, or pass --idp-entity-id/--idp-sso-url/--idp-cert-file.[/red]"
        )
        raise typer.Exit(code=1)

    config: dict[str, str] = {
        "idp_entity_id": entity_id,
        "idp_sso_url": sso_url,
        "idp_x509_cert": cert,
    }
    if parsed.get("idp_slo_url"):
        config["idp_slo_url"] = parsed["idp_slo_url"]
    if email_attribute:
        config["email_attribute"] = email_attribute
    if groups_attribute:
        config["groups_attribute"] = groups_attribute

    conn = _store().create_connection(
        tenant_id=tenant,
        type="saml",
        config=config,
        secrets={},
        domains=[],
        group_mapping=_parse_group_map(group_map or []),
    )
    console.print(f"[green]Created SAML connection[/green] [bold]{conn.id}[/bold] for org {tenant}")
    console.print("\n[bold]Configure these in the IdP:[/bold]")
    console.print("  ACS (Reply) URL:  [cyan]<base_url>/auth/saml/acs[/cyan]")
    console.print("  SP Entity ID:     [cyan]<base_url>/auth/saml/acs[/cyan] (default)")
    console.print("  NameID format:    [cyan]emailAddress[/cyan]")
    console.print(
        "\nSAML is [bold]SP-initiated only[/bold] (IdP-initiated is refused). Then verify a "
        "domain ([cyan]add-domain[/cyan] → publish TXT → [cyan]verify-domain[/cyan])."
    )
```

- [ ] **Step 4: Run — expect PASS** (the local `requires_metadata_or_flags` +
`mutually_exclusive` tests; the onelogin ones run in CI).
Run: `pytest tests/unit/test_auth_connection_cli.py -q -k create_saml`

- [ ] **Step 5: Commit** — `feat(cli): create-saml --idp-metadata-url/--idp-metadata-file (#1342)`

---

### Task 4: Docs + CHANGELOG + bump

**Files:** `docs/reference/enterprise-sso.md`, `CHANGELOG.md`, then `/bump patch`.

- [ ] **Step 1: Flip the conformance-matrix row** — change
`| IdP metadata auto-import | ❌ | Provide entity id / SSO URL / cert explicitly (create-saml) |`
to `✅` with: "✅ | `create-saml --idp-metadata-url <https>` (SSRF-guarded fetch) or
`--idp-metadata-file <path>` parses the IdP's metadata into entity id / SSO URL / cert
(+ SLO URL); explicit flags override". Update the create-saml row in the Setup table to
mention the metadata flags.
- [ ] **Step 2: CHANGELOG** `Added` (create-saml IdP-metadata import, SSRF-guarded) + an Agent
Guidance bullet (an agent can create a SAML connection from an IdP metadata URL/file; the URL
fetch is https-only + private-IP-blocked + no-redirect + size-capped; XML parsing is delegated
to python3-saml).
- [ ] **Step 3:** `/bump patch` → v0.81.80.
- [ ] **Step 4:** commit handled by the ship step (Task 5).

---

### Task 5: Gates + independent review + ship

- [ ] **Step 1:** `ruff check src/ tests/ --fix && ruff format src/ tests/`; `mypy src/dazzle`.
- [ ] **Step 2:** drift/policy gates (incl. `test_no_bare_except_pass` — the `parse` `except
Exception` re-raises a typed error, so it's compliant; the `# noqa: BLE001` documents intent);
`mkdocs build --strict`; `dazzle inspect api runtime-urls --diff` (No drift — no new routes).
- [ ] **Step 3:** `pytest tests/ -m "not e2e" -q` (local: validate/fetch + CLI error paths
pass; onelogin parse/CLI-file tests skip). No DB change → the `-m postgres` slice isn't
required, but run it if convenient.
- [ ] **Step 4: Independent review** — `feature-dev:code-reviewer` over the diff, focused on:
(a) the **SSRF guard** — https-only, all of private/loopback/link-local/reserved/multicast/
unspecified rejected, `follow_redirects=False`, timeout present, size cap, validator-before-
network; any bypass (e.g. DNS-rebinding note, IPv6-mapped IPv4, redirect re-validation);
(b) **XML parse fully delegated** to python3-saml (no hand-rolled lxml/ElementTree → no XXE);
(c) the merge/override logic + the typed-error normalisation. Fix CRITICAL/HIGH before ship.
- [ ] **Step 5: Ship** — acquire `.dazzle/improve.lock`; commit (docs/bump); tag `v0.81.80`;
push + tags; watch CI (esp. the `[saml]` job that runs the onelogin parser tests) + the tag
release; release the lock; clean worktree.
- [ ] **Step 6: Close-out** — comment the increment on #1342 (note 1/4 of the SAML cluster
done); update memory.

## Self-review (plan vs spec)

- **Coverage:** module (T1), parser tests (T2), CLI (T3), docs/changelog (T4), review+ship
  (T5) — every spec section maps to a task.
- **Type consistency:** `validate_metadata_url(url) -> None`, `fetch_idp_metadata(url, *,
  timeout) -> str`, `parse_idp_metadata_xml(xml) -> dict[str,str]`, `SamlMetadataError(reason,
  message)` — consistent across module, CLI, tests.
- **Placeholder scan:** none — code is concrete. Verify-at-impl note: the exact onelogin
  parser key names (`idp.entityId` / `singleSignOnService.url` / `x509cert`) are validated only
  in CI (onelogin not installed locally); keep `parse_idp_metadata_xml` extraction minimal and
  adjust against the first CI run if a key differs.
