# SAML SP-signed AuthnRequests (Feature C) — Implementation Plan

> **For agentic workers:** execute task-by-task. Steps use checkbox (`- [ ]`) syntax.
> Spec: `docs/superpowers/specs/2026-06-07-saml-sp-signed-authnrequests-design.md`.

**Goal:** Per-connection SP RSA keypair → sign outbound AuthnRequests (`authnRequestsSigned`),
advertise the signing cert in connection-aware SP metadata. Response signature stays the
trust anchor.

**Architecture:** `saml_sp_keys.generate_sp_keypair` (onelogin-free); store
`enable_/disable_connection_request_signing` (sp_private_key→encrypted secrets, sp_cert +
sign_requests→config, one tx); `_settings` adds the signing branch; `sp_metadata(connection=)`
+ `?connection=<id>` route; enable/disable CLI.

**Tech Stack:** Python 3.12, `cryptography` ([sso] dep), python3-saml ([saml] — now in CI via
#1345), psycopg3 store, Typer, pytest.

**Execution mode:** Hybrid (inline) per global CLAUDE.md — implement inline, then an
independent review (crypto + key-at-rest + trust-path).

---

### Task 1: `saml_sp_keys.generate_sp_keypair`

**Files:**
- Create: `src/dazzle/back/runtime/auth/saml_sp_keys.py`
- Test: `tests/unit/test_saml_sp_keys.py`

- [ ] **Step 1: Write the failing test (local — cryptography only, no onelogin)**

```python
# tests/unit/test_saml_sp_keys.py
"""SP keypair generation for SAML request signing (#1342)."""

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import NameOID

from dazzle.back.runtime.auth.saml_sp_keys import generate_sp_keypair


def test_generate_sp_keypair_shapes() -> None:
    key_pem, cert_pem = generate_sp_keypair("https://app.test/auth/saml/acs")
    key = load_pem_private_key(key_pem.encode(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    assert key.key_size == 2048
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    # self-signed: issuer == subject
    assert cert.issuer == cert.subject
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    assert cn == "https://app.test/auth/saml/acs"


def test_generate_sp_keypair_unique() -> None:
    k1, _ = generate_sp_keypair("x")
    k2, _ = generate_sp_keypair("x")
    assert k1 != k2  # fresh key each call
```

- [ ] **Step 2: Run — FAIL.** `pytest tests/unit/test_saml_sp_keys.py -q`

- [ ] **Step 3: Implement**

```python
# src/dazzle/back/runtime/auth/saml_sp_keys.py
"""SP keypair generation for SAML SP-signed AuthnRequests / encrypted assertions (#1342).

A per-connection RSA-2048 keypair + self-signed X.509 cert. The IdP imports the cert (SP
certs are conventionally self-signed — no CA chain). Pure + onelogin-free (uses
`cryptography`, the [sso] dep already used for secret-at-rest), so it's locally testable
without libxmlsec1. The private key PEM is unencrypted in memory; the caller encrypts it
at rest (connection secrets, AES-256-GCM).
"""

from __future__ import annotations

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_VALIDITY_DAYS = 3650  # ~10 years; re-issue via disable→enable


def generate_sp_keypair(common_name: str) -> tuple[str, str]:
    """Return (private_key_pem, cert_pem): an RSA-2048 key + a self-signed cert whose
    subject/issuer CN is ``common_name`` (the SP entityId)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    # Fixed epoch-based validity window — generation must be deterministic-ish and not
    # depend on wall clock semantics beyond "valid now"; use timezone-aware UTC.
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=_VALIDITY_DAYS))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return key_pem, cert_pem
```

- [ ] **Step 4: Run — PASS.** `pytest tests/unit/test_saml_sp_keys.py -q`
- [ ] **Step 5: Commit** — `feat(auth): SP keypair generation for SAML request signing (#1342)`

---

### Task 2: Store enable/disable signing material

**Files:**
- Modify: `src/dazzle/back/runtime/auth/store.py`
- Test: `tests/integration/test_connections_pg.py`

- [ ] **Step 1: Write failing PG tests** (append)

```python
def test_enable_request_signing_persists_encrypted(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="saml",
        config={"idp_entity_id": "i", "idp_sso_url": "u", "idp_x509_cert": "c"},
        secrets={}, domains=[],
    )
    assert store.enable_connection_request_signing(
        conn.id, sp_cert="CERTPEM", sp_private_key="KEYPEM"
    )
    got = store.get_connection(conn.id)
    assert got.config["sp_cert"] == "CERTPEM"
    assert got.config["sign_requests"] == "true"
    assert got.secrets["sp_private_key"] == "KEYPEM"
    assert "KEYPEM" not in repr(got)  # masked
    # not in the raw row as plaintext
    with psycopg.connect(store_url) as c:
        row = c.execute(
            "SELECT config, encrypted_secret FROM connections WHERE id=%s", (conn.id,)
        ).fetchone()
    assert "KEYPEM" not in (row[0] or "") and "KEYPEM" not in (row[1] or "")


def test_disable_request_signing_clears(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="saml",
        config={"idp_entity_id": "i", "idp_sso_url": "u", "idp_x509_cert": "c"},
        secrets={}, domains=[],
    )
    store.enable_connection_request_signing(conn.id, sp_cert="CERT", sp_private_key="KEY")
    assert store.disable_connection_request_signing(conn.id) is True
    got = store.get_connection(conn.id)
    assert "sp_cert" not in got.config and "sign_requests" not in got.config
    assert "sp_private_key" not in (got.secrets or {})
    # idempotent
    assert store.disable_connection_request_signing(conn.id) is False


def test_enable_request_signing_tenant_fenced(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="saml",
        config={"idp_entity_id": "i", "idp_sso_url": "u", "idp_x509_cert": "c"},
        secrets={}, domains=[],
    )
    assert (
        store.enable_connection_request_signing(
            conn.id, sp_cert="C", sp_private_key="K", tenant_id="org-2"
        )
        is False
    )
```

- [ ] **Step 2: Run — FAIL.**
`DATABASE_URL=postgresql://localhost/dazzle_dev pytest tests/integration/test_connections_pg.py -q -k "request_signing"`

- [ ] **Step 3: Add the store methods** (near `update_connection_secrets` in store.py). Each
reads current config + secrets, merges, writes both in one `_transaction`. Use a private
helper to read+merge:

```python
    def _write_connection_config_and_secrets(
        self, cur: Any, connection_id: str, config: dict[str, Any], secrets: dict[str, Any]
    ) -> None:
        import json

        from dazzle.back.runtime.auth.connection_crypto import encrypt_secret

        encrypted = encrypt_secret(json.dumps(secrets)) if secrets else None
        cur.execute(
            "UPDATE connections SET config = %s, encrypted_secret = %s, updated_at = %s "
            "WHERE id = %s",
            (json.dumps(config), encrypted, datetime.now(UTC).isoformat(), connection_id),
        )

    def _load_config_secrets(self, cur: Any, connection_id: str, tenant_id: str | None):
        """(config, secrets) dicts for a connection inside a tx, or (None, None)."""
        import json

        from dazzle.back.runtime.auth.connection_crypto import decrypt_secret

        if tenant_id is not None:
            cur.execute(
                "SELECT config, encrypted_secret FROM connections WHERE id = %s AND tenant_id = %s",
                (connection_id, tenant_id),
            )
        else:
            cur.execute(
                "SELECT config, encrypted_secret FROM connections WHERE id = %s",
                (connection_id,),
            )
        row = cur.fetchone()
        if row is None:
            return None, None
        config = json.loads(row["config"]) if row["config"] else {}
        enc = row["encrypted_secret"]
        secrets = json.loads(decrypt_secret(enc)) if enc else {}
        return config, secrets

    def enable_connection_request_signing(
        self, connection_id: str, *, sp_cert: str, sp_private_key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Persist SP signing material (sp_cert + sign_requests → config; sp_private_key →
        encrypted secrets) in one transaction. Returns True if a row changed."""
        with self._transaction() as cur:
            config, secrets = self._load_config_secrets(cur, connection_id, tenant_id)
            if config is None:
                return False
            config["sp_cert"] = sp_cert
            config["sign_requests"] = "true"
            secrets["sp_private_key"] = sp_private_key
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
        return True

    def disable_connection_request_signing(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> bool:
        """Remove sp_cert + sign_requests from config and sp_private_key from secrets.
        Returns True iff signing was on."""
        with self._transaction() as cur:
            config, secrets = self._load_config_secrets(cur, connection_id, tenant_id)
            if config is None or not config.get("sign_requests"):
                return False
            config.pop("sp_cert", None)
            config.pop("sign_requests", None)
            secrets.pop("sp_private_key", None)
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
        return True
```

(`_transaction` yields dict-row cursors — `row["config"]` — confirmed by the existing
`rotate_connection_secret` / `delete_membership` usage.)

- [ ] **Step 4: Run — PASS.**
`DATABASE_URL=postgresql://localhost/dazzle_dev pytest tests/integration/test_connections_pg.py -q -k "request_signing"`
- [ ] **Step 5: Commit** — `feat(auth): store enable/disable SAML request-signing material (#1342)`

---

### Task 3: `_settings` signing branch + connection-aware metadata

**Files:**
- Modify: `src/dazzle/back/runtime/auth/saml_provider.py`
- Test: `tests/unit/test_saml_provider.py` (CI onelogin) + a settings-shape test that needs no onelogin

- [ ] **Step 1: Add the `_settings` branch.** Before `return {...}` is built, capture the dict
in a variable and append the signing branch:

```python
        settings = {
            "strict": True,
            "sp": { ... unchanged ... },
            "idp": { ... unchanged ... },
            "security": { ... unchanged ... },
        }
        sp_cert = cfg.get("sp_cert")
        sp_key = (connection.secrets or {}).get("sp_private_key")
        if cfg.get("sign_requests") and sp_cert and sp_key:
            settings["sp"]["x509cert"] = sp_cert
            settings["sp"]["privateKey"] = sp_key
            settings["security"]["authnRequestsSigned"] = True
            settings["security"]["signatureAlgorithm"] = (
                "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
            )
            settings["security"]["digestAlgorithm"] = "http://www.w3.org/2001/04/xmlenc#sha256"
        return settings
```

- [ ] **Step 2: Connection-aware metadata.** Add an SP-only settings builder that optionally
folds in the signing cert, and thread `connection` through `sp_metadata`:

```python
    def _sp_only_settings(self, request: Any, connection: ConnectionRecord | None = None) -> dict[str, Any]:
        acs = self._acs_url(request)
        entity = self._sp_entity_id(connection, request) if connection is not None else acs
        settings: dict[str, Any] = {
            "strict": True,
            "sp": {
                "entityId": entity,
                "assertionConsumerService": {"url": acs, "binding": _BINDING_POST},
                "NameIDFormat": _NAMEID_EMAIL,
            },
        }
        if connection is not None:
            cfg = connection.config or {}
            if cfg.get("sign_requests") and cfg.get("sp_cert"):
                settings["sp"]["x509cert"] = cfg["sp_cert"]
                settings["security"] = {"authnRequestsSigned": True}
        return settings

    def sp_metadata(self, request: Any, connection: ConnectionRecord | None = None) -> str:
        """... (existing docstring) ... When ``connection`` has request-signing enabled,
        the metadata advertises its signing KeyDescriptor (public cert only)."""
        settings = self._build_sp_settings(self._sp_only_settings(request, connection))
        metadata = settings.get_sp_metadata()
        errors = settings.validate_metadata(metadata)
        if errors:
            raise RuntimeError(f"generated SP metadata failed validation: {errors}")
        return metadata.decode("utf-8") if isinstance(metadata, bytes) else metadata
```

- [ ] **Step 3: Tests.** In test_saml_provider.py (these use the real onelogin in CI):

```python
def test_settings_signs_requests_when_enabled() -> None:
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider
    conn = _conn(config={..., "sign_requests": "true", "sp_cert": "CERT"}, secrets={"sp_private_key": "KEY"})
    s = NativeSAMLProvider()._settings(conn, _req())
    assert s["security"]["authnRequestsSigned"] is True
    assert s["sp"]["x509cert"] == "CERT" and s["sp"]["privateKey"] == "KEY"
    assert s["security"]["wantAssertionsSigned"] is True  # unchanged

def test_settings_no_signing_by_default() -> None:
    pytest.importorskip("onelogin")
    ...
    s = NativeSAMLProvider()._settings(_conn(), _req())
    assert "authnRequestsSigned" not in s["security"]
    assert "privateKey" not in s["sp"]

def test_metadata_advertises_signing_cert() -> None:
    pytest.importorskip("onelogin")
    conn = _conn(config={..., "sign_requests": "true", "sp_cert": <a real cert PEM via generate_sp_keypair>})
    xml = NativeSAMLProvider().sp_metadata(_req(), conn)
    assert "use=\"signing\"" in xml
```

Reuse the file's existing `_conn`/`_req` helpers (extend `_conn` to accept config/secrets
overrides if it doesn't already). For the metadata test, generate a real cert with
`generate_sp_keypair` so python3-saml accepts it.

- [ ] **Step 4: Run.** `pytest tests/unit/test_saml_provider.py -q` (now runs onelogin in CI;
locally too, since the venv has python3-saml).
- [ ] **Step 5: Commit** — `feat(auth): sign AuthnRequests + advertise signing cert in metadata (#1342)`

---

### Task 4: Metadata route `?connection=<id>`

**Files:** Modify `src/dazzle/back/runtime/auth/saml_routes.py`

- [ ] **Step 1: Thread the optional connection param** into `saml_metadata`:

```python
    @router.get("/auth/saml/metadata")
    async def saml_metadata(request: Request, connection: str = "") -> Response:
        from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider

        conn = None
        if connection:
            store = request.app.state.auth_store
            conn = store.get_connection(connection)  # unknown id → None → app-level fallback
        try:
            xml = NativeSAMLProvider().sp_metadata(request, conn)
        except Exception as exc:  # noqa: BLE001 — never 500-leak a stack trace
            _logger.warning("SAML metadata generation failed: %s", exc)  # nosemgrep
            return Response(content="SAML SP metadata unavailable", status_code=503, media_type="text/plain")
        return Response(content=xml, media_type="application/samlmetadata+xml")
```

(`connection` is a FastAPI query param. Unknown id → `conn=None` → app-level metadata, per
the spec's resolved open question.)

- [ ] **Step 2: Test** in `tests/integration/test_saml_routes.py` (CI onelogin): a GET with
`?connection=<signing-conn-id>` returns 200 and the body contains `use="signing"`; a GET with
`?connection=bogus` returns 200 app-level metadata (no signing KeyDescriptor); plain GET
unchanged. Use the file's existing fake store + add `get_connection` returning a signing conn.
- [ ] **Step 3: Commit** — `feat(auth): /auth/saml/metadata?connection=<id> signing metadata (#1342)`

---

### Task 5: CLI enable/disable-request-signing

**Files:**
- Modify: `src/dazzle/cli/auth_connection.py`
- Test: `tests/unit/test_auth_connection_cli.py`

- [ ] **Step 1: Write failing CLI tests.** Extend the fake `_Store` with
`enable_connection_request_signing`/`disable_connection_request_signing` (record calls,
return True) and `_Conn` to carry `config`. Tests:

```python
def test_enable_request_signing_saml(monkeypatch) -> None:
    store = _Store(conn=_Conn("c1", conn_type="saml"))
    _patch_store(monkeypatch, store)
    r = runner.invoke(auth_app, ["connection", "enable-request-signing", "c1"])
    assert r.exit_code == 0 and "signing" in r.output.lower()
    assert store.signing_enabled  # records sp_cert + sp_private_key were passed

def test_enable_request_signing_rejects_oidc(monkeypatch) -> None:
    _patch_store(monkeypatch, _Store(conn=_Conn("c1", conn_type="oidc")))
    r = runner.invoke(auth_app, ["connection", "enable-request-signing", "c1"])
    assert r.exit_code == 1 and "saml" in r.output.lower()

def test_enable_request_signing_missing(monkeypatch) -> None:
    _patch_store(monkeypatch, _Store(conn=None))
    r = runner.invoke(auth_app, ["connection", "enable-request-signing", "cx"])
    assert r.exit_code == 1 and "No connection" in r.output

def test_disable_request_signing(monkeypatch) -> None:
    store = _Store(conn=_Conn("c1", conn_type="saml"))
    _patch_store(monkeypatch, store)
    r = runner.invoke(auth_app, ["connection", "disable-request-signing", "c1"])
    assert r.exit_code == 0
```

The fake `enable_connection_request_signing(self, cid, *, sp_cert, sp_private_key,
tenant_id=None)` sets `self.signing_enabled = True` and asserts both PEMs are non-empty.

- [ ] **Step 2: Run — FAIL.** `pytest tests/unit/test_auth_connection_cli.py -q -k request_signing`

- [ ] **Step 3: Add the commands** (auth_connection.py):

```python
@connection_app.command("enable-request-signing")
def enable_request_signing(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Generate an SP keypair and sign this connection's AuthnRequests (SAML only).

    Re-import the connection's metadata at the IdP afterwards (see the printed URL) so it
    trusts the SP signing cert. Re-run after disabling to rotate the key."""
    from dazzle.back.runtime.auth.saml_sp_keys import generate_sp_keypair

    store = _store()
    conn = store.get_connection(connection_id)
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    if conn.type != "saml":
        console.print(f"[red]Connection {connection_id!r} is {conn.type!r} — request signing is SAML-only[/red]")
        raise typer.Exit(code=1)
    if (conn.config or {}).get("sign_requests"):
        console.print(f"[yellow]Request signing already enabled[/yellow] for {connection_id} (disable→enable to rotate).")
        raise typer.Exit(code=0)
    cn = (conn.config or {}).get("sp_entity_id") or f"{connection_id}"
    key_pem, cert_pem = generate_sp_keypair(cn)
    if not store.enable_connection_request_signing(connection_id, sp_cert=cert_pem, sp_private_key=key_pem):
        console.print(f"[red]Failed to enable request signing for {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Request signing enabled[/green] for connection {connection_id}.")
    console.print("Re-import this connection's SP metadata at the IdP so it trusts the signing cert:")
    console.print(f"  [cyan]<base_url>/auth/saml/metadata?connection={connection_id}[/cyan]")


@connection_app.command("disable-request-signing")
def disable_request_signing(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Stop signing this connection's AuthnRequests and drop the SP keypair."""
    store = _store()
    if store.disable_connection_request_signing(connection_id):
        console.print(f"[green]Request signing disabled[/green] for connection {connection_id}.")
    else:
        console.print(f"[yellow]Request signing was not enabled[/yellow] for {connection_id}.")
```

- [ ] **Step 4: Run — PASS.** `pytest tests/unit/test_auth_connection_cli.py -q -k request_signing`
- [ ] **Step 5: Commit** — `feat(cli): enable/disable-request-signing for SAML (#1342)`

---

### Task 6: Docs + CHANGELOG + bump

- [ ] **Step 1:** `docs/reference/enterprise-sso.md` — flip
`| SP-signed AuthnRequests | ❌ | Deferred (the Response signature is the trust anchor) |`
to `✅` with a note (per-connection keypair via `enable-request-signing`; Response signature
remains the trust anchor; re-import `?connection=<id>` metadata at the IdP). Mention the two
commands + the `?connection=` metadata variant in the surrounding prose.
- [ ] **Step 2:** CHANGELOG `Added` (per-connection SP keypair + signed AuthnRequests +
connection-aware metadata + enable/disable CLI) + Agent Guidance bullet (private key encrypted
at rest, never rendered; re-import metadata at the IdP; Response signature still the anchor).
- [ ] **Step 3:** `/bump patch` → v0.81.83.

---

### Task 7: Gates + independent review + ship

- [ ] **Step 1:** `ruff … --fix && ruff format`; `mypy src/dazzle`.
- [ ] **Step 2:** drift/policy gates (incl. `test_no_bare_except_pass` — the provider's
existing `except Exception` re-raise is unchanged); `mkdocs build --strict`;
`dazzle inspect api runtime-urls --diff` (the metadata route gains a query param, not a new
path → expect No drift; if it drifts, regenerate baseline + CHANGELOG note).
- [ ] **Step 3:** `pytest tests/ -m "not e2e" -q` (local: keypair + CLI + settings/metadata,
which now run since the venv has python3-saml) AND
`DATABASE_URL=…/dazzle_dev pytest -m postgres -q` (store).
- [ ] **Step 4: Independent review** — `feature-dev:code-reviewer`, focus: (a) keypair gen
(RSA-2048, self-signed, SHA-256, PKCS8, validity); (b) `sp_private_key` only ever in the
encrypted secrets blob — never in config, metadata XML, logs, or CLI output (grep the diff);
(c) `_settings` doesn't weaken response validation (wantAssertionsSigned /
rejectUnsolicitedResponsesWithInResponseTo unchanged); (d) the public `?connection=` metadata
route exposes only the public cert and an unknown id can't leak/enumerate. Fix CRITICAL/HIGH.
- [ ] **Step 5: Ship** — lock; commit (docs/bump); tag v0.81.83; push + tags; watch CI (the
`[saml]` job runs the new settings/metadata tests) + tag release; release lock; clean worktree.
- [ ] **Step 6: Close-out** — comment #1342 (SAML cluster 2/4 done); update memory.

## Self-review (plan vs spec)

- **Coverage:** keypair (T1), store (T2), settings+metadata (T3), route (T4), CLI (T5),
  docs (T6), review+ship (T7) — every spec section mapped.
- **Type consistency:** `generate_sp_keypair(common_name) -> (str,str)`;
  `enable_connection_request_signing(id, *, sp_cert, sp_private_key, tenant_id=None) -> bool`;
  `disable_…(id, *, tenant_id=None) -> bool`; `sp_metadata(request, connection=None) -> str`;
  config keys `sp_cert`/`sign_requests`, secret key `sp_private_key` — consistent across tasks.
- **Placeholder scan:** none. Verify-at-impl note: confirm `test_saml_provider.py`'s `_conn`/
  `_req` helper signatures and extend for config/secrets overrides (read before writing T3
  tests).
