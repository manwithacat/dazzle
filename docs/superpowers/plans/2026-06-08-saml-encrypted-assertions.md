# SAML Encrypted Assertions (feature B) Implementation Plan

> **For agentic workers:** Execute Hybrid (inline) per the project's model policy, with an
> independent security review at the checkpoint marked below. Steps use checkbox (`- [ ]`).

**Goal:** Opt a SAML connection into encrypted assertions (`wantAssertionsEncrypted`),
reusing C's SP keypair, via `enable-/disable-assertion-encryption`.

**Architecture:** A new `encrypt_assertions` config flag parallels C's `sign_requests`;
both share one SP keypair whose lifecycle is decoupled so it survives while *either* feature
is on. python3-saml decrypts with `sp.privateKey` and auto-advertises the encryption
KeyDescriptor in SP metadata.

**Tech Stack:** python3-saml ([saml] extra), psycopg3 auth store, typer CLI.

**Spec:** `docs/superpowers/specs/2026-06-08-saml-encrypted-assertions-design.md`

---

## File Structure

- Modify `src/dazzle/http/runtime/auth/secret_rotation.py` — 2 new audit-event constants.
- Modify `src/dazzle/http/runtime/auth/store.py` — keypair-lifecycle helpers + refactor
  signing enable/disable + 2 new encryption methods.
- Modify `src/dazzle/http/runtime/auth/saml_provider.py` — `_settings` +
  `_sp_only_settings` encryption wiring.
- Modify `src/dazzle/cli/auth_connection.py` — 2 new commands.
- Modify `tests/unit/test_saml_provider.py`, `tests/unit/test_auth_connection_cli.py`,
  `tests/integration/test_connections_pg.py`.

---

### Task 1: Audit-event constants

**Files:** Modify `src/dazzle/http/runtime/auth/secret_rotation.py`

- [ ] **Step 1: Add the constants** after `SECRET_EVENT_SIGNING_DISABLED` (line 19):

```python
SECRET_EVENT_ENCRYPTION_ENABLED = "sp_encryption_enabled"
SECRET_EVENT_ENCRYPTION_DISABLED = "sp_encryption_disabled"
```

- [ ] **Step 2: Verify** `python -c "from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_ENCRYPTION_ENABLED"`

---

### Task 2: Store — shared keypair lifecycle + encryption methods

**Files:** Modify `src/dazzle/http/runtime/auth/store.py`

- [ ] **Step 1: Write the failing test** (PG round-trip — append to
`tests/integration/test_connections_pg.py`). This pins the lifecycle decoupling, the core
regression risk:

```python
def test_encryption_and_signing_share_one_keypair(store_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(store_url)
    conn = store.create_connection(
        tenant_id="org-enc", type="saml", provider="native",
        config={"idp_entity_id": "x", "idp_sso_url": "y", "idp_x509_cert": "z"},
        secrets={}, domains=[], group_mapping={},
    )
    # Enable signing → keypair written.
    assert store.enable_connection_request_signing(
        conn.id, sp_cert="CERT", sp_private_key="KEY")
    # Enable encryption → reuses the SAME keypair, sets the flag.
    assert store.enable_connection_assertion_encryption(
        conn.id, sp_cert="CERT2", sp_private_key="KEY2")
    got = store.get_connection(conn.id)
    assert got.config["encrypt_assertions"] == "true"
    assert got.config["sign_requests"] == "true"
    assert got.config["sp_cert"] == "CERT"          # NOT clobbered by the 2nd enable
    assert got.secrets["sp_private_key"] == "KEY"
    # Disable signing → keypair SURVIVES (encryption still on).
    assert store.disable_connection_request_signing(conn.id)
    got = store.get_connection(conn.id)
    assert "sign_requests" not in got.config
    assert got.config.get("sp_cert") == "CERT"       # kept for encryption
    assert got.secrets.get("sp_private_key") == "KEY"
    # Disable encryption → now both off → keypair removed.
    assert store.disable_connection_assertion_encryption(conn.id)
    got = store.get_connection(conn.id)
    assert "encrypt_assertions" not in got.config
    assert "sp_cert" not in got.config
    assert "sp_private_key" not in got.secrets
    # Audit trail recorded both feature toggles.
    events = {e["event"] for e in store.get_connection_secret_events(conn.id)}
    assert {"sp_signing_enabled", "sp_signing_disabled",
            "sp_encryption_enabled", "sp_encryption_disabled"} <= events
```

- [ ] **Step 2: Run** `DATABASE_URL=postgresql://localhost/dazzle_dev pytest tests/integration/test_connections_pg.py::test_encryption_and_signing_share_one_keypair -q` → FAIL (no `enable_connection_assertion_encryption`).

- [ ] **Step 3: Add the keypair helpers** (private methods on `AuthStore`, near the signing
methods ~line 1474). These centralise the "write iff absent / remove iff neither feature"
rules:

```python
    @staticmethod
    def _ensure_sp_keypair(
        config: dict[str, Any], secrets: dict[str, Any], *, sp_cert: str, sp_private_key: str
    ) -> None:
        """Write the shared SP keypair only if absent — never clobber an existing key, so
        enabling the second feature (sign/encrypt) keeps the first feature's key. Rotation
        stays explicit (disable both, then re-enable)."""
        config.setdefault("sp_cert", sp_cert)
        secrets.setdefault("sp_private_key", sp_private_key)

    @staticmethod
    def _maybe_remove_sp_keypair(config: dict[str, Any], secrets: dict[str, Any]) -> None:
        """Drop the shared SP keypair iff NEITHER feature uses it any more."""
        if not config.get("sign_requests") and not config.get("encrypt_assertions"):
            config.pop("sp_cert", None)
            secrets.pop("sp_private_key", None)
```

- [ ] **Step 4: Refactor `enable_connection_request_signing`** — replace the two direct
keypair writes (`config["sp_cert"] = sp_cert` / `secrets["sp_private_key"] = sp_private_key`)
with the helper:

```python
            config["sign_requests"] = "true"
            self._ensure_sp_keypair(
                config, secrets, sp_cert=sp_cert, sp_private_key=sp_private_key
            )
```
(Keep the `conn_type != "saml"` guard and the audit write unchanged.)

- [ ] **Step 5: Refactor `disable_connection_request_signing`** — pop only the flag, then
delegate keypair removal:

```python
            if config is None or not config.get("sign_requests"):
                return False
            config.pop("sign_requests", None)
            self._maybe_remove_sp_keypair(config, secrets)
```
(The `config.pop("sp_cert")` / `secrets.pop("sp_private_key")` lines are removed — the helper
owns that now.)

- [ ] **Step 6: Add `enable_connection_assertion_encryption`** (mirror signing enable):

```python
    def enable_connection_assertion_encryption(
        self,
        connection_id: str,
        *,
        sp_cert: str,
        sp_private_key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Persist SAML assertion-encryption material (#1342 feature B): set
        ``encrypt_assertions='true'`` and ensure the shared SP keypair. Returns True if a
        row changed. SAML-only; tenant-fenced when given."""
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_ENCRYPTION_ENABLED

        with self._transaction() as cur:
            config, secrets, ten, conn_type = self._load_config_secrets(
                cur, connection_id, tenant_id
            )
            if config is None:
                return False
            if conn_type != "saml":
                raise ValueError(
                    f"assertion encryption is SAML-only (connection {connection_id!r} "
                    f"is {conn_type!r})"
                )
            config["encrypt_assertions"] = "true"
            self._ensure_sp_keypair(
                config, secrets, sp_cert=sp_cert, sp_private_key=sp_private_key
            )
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=ten or "",
                event=SECRET_EVENT_ENCRYPTION_ENABLED,
                actor="cli",
                detail={"type": conn_type},
                at=datetime.now(UTC).isoformat(),
            )
        return True
```

- [ ] **Step 7: Add `disable_connection_assertion_encryption`** (mirror signing disable):

```python
    def disable_connection_assertion_encryption(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> bool:
        """Remove ``encrypt_assertions`` and drop the shared SP keypair iff signing is also
        off (one transaction). Returns True iff encryption was on."""
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_ENCRYPTION_DISABLED

        with self._transaction() as cur:
            config, secrets, ten, conn_type = self._load_config_secrets(
                cur, connection_id, tenant_id
            )
            if config is None or not config.get("encrypt_assertions"):
                return False
            config.pop("encrypt_assertions", None)
            self._maybe_remove_sp_keypair(config, secrets)
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=ten or "",
                event=SECRET_EVENT_ENCRYPTION_DISABLED,
                actor="cli",
                detail={"type": conn_type},
                at=datetime.now(UTC).isoformat(),
            )
        return True
```

- [ ] **Step 8: Run** the Step-1 test → PASS. Also run the existing signing PG tests to
confirm the refactor didn't regress C:
`DATABASE_URL=… pytest tests/integration/test_connections_pg.py -q`

---

### Task 3: Provider settings — wantAssertionsEncrypted + metadata cert

**Files:** Modify `src/dazzle/http/runtime/auth/saml_provider.py`

- [ ] **Step 1: Write failing tests** (append to `tests/unit/test_saml_provider.py`):

```python
def test_encrypt_assertions_sets_want_encrypted() -> None:
    p = NativeSAMLProvider()
    conn = _conn(
        config={
            "idp_entity_id": "x", "idp_sso_url": "y", "idp_x509_cert": "z",
            "encrypt_assertions": "true", "sp_cert": "CERT",
        },
        secrets={"sp_private_key": "KEY"},
    )
    s = p._settings(conn, _FakeRequest())
    assert s["security"]["wantAssertionsEncrypted"] is True
    assert s["sp"]["x509cert"] == "CERT"
    assert s["sp"]["privateKey"] == "KEY"


def test_no_encrypt_flag_leaves_want_encrypted_unset() -> None:
    s = NativeSAMLProvider()._settings(_conn(), _FakeRequest())
    assert "wantAssertionsEncrypted" not in s["security"]


def test_encrypt_and_sign_compose_on_shared_keypair() -> None:
    conn = _conn(
        config={
            "idp_entity_id": "x", "idp_sso_url": "y", "idp_x509_cert": "z",
            "sign_requests": "true", "encrypt_assertions": "true", "sp_cert": "CERT",
        },
        secrets={"sp_private_key": "KEY"},
    )
    s = NativeSAMLProvider()._settings(conn, _FakeRequest())
    assert s["security"]["authnRequestsSigned"] is True
    assert s["security"]["wantAssertionsEncrypted"] is True


def test_sp_only_settings_advertises_cert_for_encryption_only() -> None:
    # Encryption-only (no signing) must still put the cert in settings so the metadata
    # carries the use="encryption" KeyDescriptor.
    conn = _conn(
        config={
            "idp_entity_id": "x", "idp_sso_url": "y", "idp_x509_cert": "z",
            "encrypt_assertions": "true", "sp_cert": "CERT",
        },
        secrets={"sp_private_key": "KEY"},
    )
    s = NativeSAMLProvider()._sp_only_settings(_FakeRequest(), conn)
    assert s["sp"]["x509cert"] == "CERT"
    assert s["sp"]["privateKey"] == "KEY"
```

- [ ] **Step 2: Run** `pytest tests/unit/test_saml_provider.py -q` → the 4 new tests FAIL.

- [ ] **Step 3: Implement in `_settings`** — after the existing `sign_requests` block (after
line 127, before `return settings`):

```python
        # Encrypted assertions (#1342, feature B): when enabled + keypair present, require
        # the assertion to be encrypted and give python3-saml the key to decrypt it. Shares
        # the keypair the sign_requests block may already have installed (set idempotently).
        if cfg.get("encrypt_assertions") and sp_cert and sp_key:
            settings["sp"]["x509cert"] = sp_cert
            settings["sp"]["privateKey"] = sp_key
            settings["security"]["wantAssertionsEncrypted"] = True
```

- [ ] **Step 4: Implement in `_sp_only_settings`** — broaden the metadata cert condition so
encryption-only connections advertise their cert. Replace the existing `if cfg.get("sign_requests") and cfg.get("sp_cert") and sp_key:` block guard with an either-feature check:

```python
            sp_key = (connection.secrets or {}).get("sp_private_key")
            wants_key = cfg.get("sign_requests") or cfg.get("encrypt_assertions")
            if wants_key and cfg.get("sp_cert") and sp_key:
                # python3-saml needs cert+key in settings; get_sp_metadata serialises only
                # the public cert (signing + encryption KeyDescriptors), never the key.
                settings["sp"]["x509cert"] = cfg["sp_cert"]
                settings["sp"]["privateKey"] = sp_key
                # authnRequestsSigned only when signing is actually on (drives the
                # AuthnRequestsSigned metadata attr); the encryption KeyDescriptor is added
                # from sp.x509cert regardless.
                if cfg.get("sign_requests"):
                    settings["security"] = {"authnRequestsSigned": True}
```

- [ ] **Step 5: Run** `pytest tests/unit/test_saml_provider.py -q` → all PASS.

---

### Task 4: CLI — enable/disable-assertion-encryption

**Files:** Modify `src/dazzle/cli/auth_connection.py`

- [ ] **Step 1: Write failing tests** (append to `tests/unit/test_auth_connection_cli.py`;
add the two fake-store methods to `_FakeStore` first):

In `_FakeStore` (near the signing fakes ~line 58):
```python
    def enable_connection_assertion_encryption(self, cid, *, sp_cert, sp_private_key, tenant_id=None):
        assert sp_cert and sp_private_key
        self.encryption_enabled = cid
        return self._conn is not None and self._conn.id == cid

    def disable_connection_assertion_encryption(self, cid, *, tenant_id=None):
        self.encryption_disabled = cid
        return True
```

Tests:
```python
def test_enable_assertion_encryption(monkeypatch) -> None:
    store = _FakeStore(_Conn("c1", type="saml"))
    _patch_store(monkeypatch, store)
    result = runner.invoke(auth_connection.connection_app, ["enable-assertion-encryption", "c1"])
    assert result.exit_code == 0
    assert store.encryption_enabled == "c1"
    assert "metadata" in result.output.lower()  # prints the re-import URL


def test_enable_assertion_encryption_rejects_non_saml(monkeypatch) -> None:
    store = _FakeStore(_Conn("c1", type="oidc"))
    _patch_store(monkeypatch, store)
    result = runner.invoke(auth_connection.connection_app, ["enable-assertion-encryption", "c1"])
    assert result.exit_code == 1
    assert getattr(store, "encryption_enabled", None) is None


def test_disable_assertion_encryption(monkeypatch) -> None:
    store = _FakeStore(_Conn("c1", type="saml"))
    _patch_store(monkeypatch, store)
    result = runner.invoke(auth_connection.connection_app, ["disable-assertion-encryption", "c1"])
    assert result.exit_code == 0
    assert store.encryption_disabled == "c1"
```
(Confirm `_Conn` accepts `type=`; if its config drives `encrypt_assertions` already-on
detection, leave config empty so the enable path runs. Match the existing
request-signing tests' `_Conn` usage.)

- [ ] **Step 2: Run** `pytest tests/unit/test_auth_connection_cli.py -q` → new tests FAIL.

- [ ] **Step 3: Implement the commands** after `disable_request_signing` (~line 311):

```python
@connection_app.command("enable-assertion-encryption")
def enable_assertion_encryption(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Require + decrypt encrypted SAML assertions on this connection (SAML only).

    Reuses the SP keypair if request-signing already created one, else generates it. After
    enabling, configure the IdP to ENCRYPT assertions and re-import this connection's SP
    metadata (printed URL) so it has the SP encryption cert. WARNING: once on, a response
    carrying a plaintext (unencrypted) assertion is rejected — enable the IdP side first.
    """
    from dazzle.http.runtime.auth.saml_sp_keys import generate_sp_keypair

    store = _store()
    conn = store.get_connection(connection_id)
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    if conn.type != "saml":
        console.print(
            f"[red]Connection {connection_id!r} is {conn.type!r} — assertion encryption is "
            "SAML-only[/red]"
        )
        raise typer.Exit(code=1)
    if (conn.config or {}).get("encrypt_assertions"):
        console.print(
            f"[yellow]Assertion encryption already enabled[/yellow] for {connection_id}."
        )
        raise typer.Exit(code=0)
    cfg = conn.config or {}
    sp_cert = cfg.get("sp_cert")
    sp_key = (conn.secrets or {}).get("sp_private_key")
    if not (sp_cert and sp_key):
        common_name = cfg.get("sp_entity_id") or connection_id
        sp_key, sp_cert = generate_sp_keypair(common_name)
    if not store.enable_connection_assertion_encryption(
        connection_id, sp_cert=sp_cert, sp_private_key=sp_key
    ):
        console.print(f"[red]Failed to enable assertion encryption for {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Assertion encryption enabled[/green] for connection {connection_id}.")
    console.print(
        "[yellow]Configure the IdP to encrypt assertions, then re-import this connection's "
        "SP metadata[/yellow] (a plaintext assertion is now rejected):"
    )
    console.print(f"  [cyan]<base_url>/auth/saml/metadata?connection={connection_id}[/cyan]")


@connection_app.command("disable-assertion-encryption")
def disable_assertion_encryption(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Stop requiring encrypted assertions (drops the SP keypair iff signing is also off)."""
    store = _store()
    if store.disable_connection_assertion_encryption(connection_id):
        console.print(
            f"[green]Assertion encryption disabled[/green] for connection {connection_id}."
        )
    else:
        console.print(
            f"[yellow]Assertion encryption was not enabled[/yellow] for {connection_id}."
        )
```

Note `generate_sp_keypair` returns `(key_pem, cert_pem)` — match C's unpack order.

- [ ] **Step 4: Run** `pytest tests/unit/test_auth_connection_cli.py -q` → all PASS.

---

### Checkpoint — independent security review

- [ ] Dispatch a `feature-dev:code-reviewer` subagent on the diff. Focus: (1) the keypair
lifecycle can never strand or leak the key — enabling B then disabling A keeps the key,
disabling both removes it, and no path writes the private key to `config`/metadata XML;
(2) the SAML-only guard holds on the new store methods; (3) `wantAssertionsEncrypted` is
purely additive to the existing signature/unsolicited anchors; (4) the strict-posture
warning is present. Fix anything CRITICAL before shipping.

---

### Task 5: Docs + ship

- [ ] **Step 1: CHANGELOG** under a new version, `### Added`: "SAML assertion encryption —
`dazzle auth connection enable-/disable-assertion-encryption` (`wantAssertionsEncrypted`,
reuses the SP keypair; strict — plaintext assertions rejected once on)." Add an
`### Agent Guidance` line if the keypair-sharing convention is worth noting.
- [ ] **Step 2:** `/bump patch`.
- [ ] **Step 3: Gates** — `ruff`, `mypy src/dazzle`, drift/policy, `pytest tests/ -m "not
e2e"`, and the postgres slice (`DATABASE_URL=…/dazzle_dev pytest -m postgres -q`) since the
store changed. The mutation gate is unaffected (no security-target module touched).
- [ ] **Step 4:** commit (verify `COMMIT_EXIT=0` before tag), tag, push, watch CI + release.
- [ ] **Step 5:** update memory `project_1342_enterprise_auth_capability` — B shipped,
A (SLO) next.

## Self-review

- **Spec coverage:** mechanism (Task 3), keypair lifecycle decouple (Task 2), surface
  (Tasks 2–4), audit (Tasks 1–2), strict-posture warning (Task 4), tests (all). ✓
- **Type consistency:** `generate_sp_keypair → (key_pem, cert_pem)` unpack order matches C
  (verified in `auth_connection.py:288`). Store method signatures mirror the signing pair. ✓
- **No placeholders:** every step has concrete code. ✓
