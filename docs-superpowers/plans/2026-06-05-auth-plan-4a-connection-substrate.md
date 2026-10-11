# Auth Plan 4a — Enterprise Connection Substrate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the foundation for per-org enterprise auth: a framework-owned, **org-fenced** `Connection` record (OIDC/SAML/SCIM config) with **secrets encrypted at rest** (AES-GCM), and a `ConnectionProvider` seam (the swappable native-vs-delegated interface) — with no live provider yet (NativeOIDCProvider is 4b, NativeSCIMProvider 4c, SAML is Plan 5).

**Architecture:** `Connection` lives in the auth-store raw-SQL world (like `memberships`/`organizations`): a `connections` table keyed to an org by `tenant_id`, with non-secret `config` (issuer, client_id, endpoints) stored plaintext and secret material (`client_secret`, SCIM bearer) stored as a single AES-GCM-encrypted blob. Encryption uses `cryptography`'s AESGCM with a 32-byte key from `DAZZLE_CONNECTION_SECRET` (env, base64), **fail-closed** — absent/invalid key → connection CRUD raises, never plaintext. Domains route to a connection only when **verified** (an unverified claimed domain can't hijack another org's SSO). The `ConnectionProvider` Protocol (`initiate`/`callback` for SSO) + an `AssertedIdentity` result + a `(type, provider)` registry form the seam; with nothing registered, `resolve_provider` raises a clear "not implemented yet" — 4b/4c register the natives.

**Tech Stack:** Python 3.12, `cryptography` AESGCM (moved into the `[sso]` extra, lazy-imported), psycopg3 (`AuthStore`), Alembic (ADR-0017), `secrets`/`base64`, pytest (`e2e`+`postgres`).

**Spec:** `docs/superpowers/specs/2026-06-05-auth-identity-model-design.md` §5 (per-org enterprise connections). Slice **4a** (substrate + seam). **4b** = NativeOIDCProvider (authlib) + domain→org routing + JIT; **4c** = NativeSCIMProvider; **Plan 5** = SAML. Distinct from `[[auth.oauth_providers]]` global social login (unchanged).

**Decisions (confirmed):** substrate + seam first; AES-GCM + env-var key, fail-closed.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/http/runtime/auth/connection_crypto.py` (**create**) | `encrypt_secret(plaintext)→token` / `decrypt_secret(token)→plaintext` via AES-GCM; key from `DAZZLE_CONNECTION_SECRET`; fail-closed. Lazy `cryptography` import. |
| `src/dazzle/http/runtime/auth/connections.py` (**create**) | `ConnectionRecord` dataclass, `CONNECTIONS_DDL`/indexes, the `ConnectionProvider` Protocol, `AssertedIdentity`, the provider registry (`register_provider`/`resolve_provider`), `ConnectionError`. |
| `src/dazzle/http/runtime/auth/store.py` (**modify**) | `_init_db` table + `create_connection`/`get_connection`/`get_connections_for_tenant`/`get_connection_by_verified_domain`/`update_connection`/`delete_connection` (encrypt on write, decrypt on read). |
| `src/dazzle/http/alembic/versions/0011_connections.py` (**create**) | Idempotent `connections` table migration (mirror `0010`). |
| `pyproject.toml` (**modify**) | Add `cryptography>=41.0.0` to the `[sso]` extra. |
| `tests/unit/test_connection_crypto.py` (**create**) | Round-trip, tamper detection, missing/short key fail-closed, distinct ciphertexts (random nonce). |
| `tests/unit/test_connection_provider.py` (**create**) | `resolve_provider` raises when unregistered; `register_provider` + resolve round-trips; `AssertedIdentity` shape. |
| `tests/integration/test_connections_pg.py` (**create**) | Real-PG: create stores secrets ENCRYPTED (plaintext never in the row); read decrypts; fenced by tenant; verified-domain routing (unverified domain does NOT match); migration applies. |

---

## Task 1: Secret encryption (`connection_crypto.py`)

**Files:**
- Create: `src/dazzle/http/runtime/auth/connection_crypto.py`
- Test: `tests/unit/test_connection_crypto.py`

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_connection_crypto.py
"""AES-GCM secret-at-rest encryption for connections (auth Plan 4a)."""

import base64
import os

import pytest

from dazzle.http.runtime.auth.connection_crypto import (
    ConnectionSecretError,
    decrypt_secret,
    encrypt_secret,
)

_KEY = base64.b64encode(b"0" * 32).decode()  # 32-byte key, base64


def _set_key(monkeypatch, key=_KEY):
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", key)


def test_round_trip(monkeypatch) -> None:
    _set_key(monkeypatch)
    token = encrypt_secret("client-secret-xyz")
    assert token != "client-secret-xyz"  # not plaintext
    assert decrypt_secret(token) == "client-secret-xyz"


def test_distinct_ciphertexts_random_nonce(monkeypatch) -> None:
    _set_key(monkeypatch)
    assert encrypt_secret("x") != encrypt_secret("x")  # random 96-bit nonce


def test_tamper_is_rejected(monkeypatch) -> None:
    _set_key(monkeypatch)
    token = encrypt_secret("secret")
    raw = bytearray(base64.b64decode(token))
    raw[-1] ^= 0x01  # flip a ciphertext/tag bit
    tampered = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(ConnectionSecretError):
        decrypt_secret(tampered)


def test_missing_key_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    with pytest.raises(ConnectionSecretError, match="DAZZLE_CONNECTION_SECRET"):
        encrypt_secret("secret")


def test_wrong_length_key_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"short").decode())
    with pytest.raises(ConnectionSecretError, match="32 bytes"):
        encrypt_secret("secret")


def test_decrypt_with_different_key_fails(monkeypatch) -> None:
    _set_key(monkeypatch)
    token = encrypt_secret("secret")
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(os.urandom(32)).decode())
    with pytest.raises(ConnectionSecretError):
        decrypt_secret(token)
```

- [ ] **Step 2: Run it to verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Create the module**

```python
# src/dazzle/http/runtime/auth/connection_crypto.py
"""Secret-at-rest encryption for enterprise connections (auth Plan 4a).

Connection secrets (OIDC ``client_secret``, SCIM bearer) are encrypted with
AES-256-GCM (authenticated encryption) under a 32-byte key from the
``DAZZLE_CONNECTION_SECRET`` env var (base64). Fail-closed: an absent or
malformed key raises ``ConnectionSecretError`` — there is no plaintext fallback,
so a misconfigured deployment cannot silently store secrets in the clear.

``cryptography`` is an enterprise-connections (``[sso]`` extra) dependency and is
imported lazily, so core installs without it are unaffected until a connection
secret is actually encrypted/decrypted.
"""

from __future__ import annotations

import base64
import os

_ENV_KEY = "DAZZLE_CONNECTION_SECRET"


class ConnectionSecretError(RuntimeError):
    """Encryption/decryption of a connection secret failed (key missing/invalid,
    or ciphertext tampered)."""


def _load_key() -> bytes:
    raw = os.environ.get(_ENV_KEY, "").strip()
    if not raw:
        raise ConnectionSecretError(
            f"{_ENV_KEY} is not set — required to encrypt connection secrets at rest"
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 — any decode failure is a config error
        raise ConnectionSecretError(f"{_ENV_KEY} is not valid base64") from exc
    if len(key) != 32:
        raise ConnectionSecretError(
            f"{_ENV_KEY} must decode to 32 bytes (AES-256), got {len(key)}"
        )
    return key


def encrypt_secret(plaintext: str) -> str:
    """Encrypt ``plaintext`` → base64(nonce ‖ ciphertext+tag). Raises on key error."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _load_key()
    nonce = os.urandom(12)  # 96-bit GCM nonce
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt a token from :func:`encrypt_secret`. Raises ``ConnectionSecretError``
    on a wrong key or tampered ciphertext (AES-GCM authentication failure)."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _load_key()
    try:
        blob = base64.b64decode(token, validate=True)
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except InvalidTag as exc:
        raise ConnectionSecretError("connection secret authentication failed (tampered or wrong key)") from exc
    except Exception as exc:  # noqa: BLE001
        raise ConnectionSecretError("connection secret could not be decrypted") from exc
```

- [ ] **Step 4: Run the test to verify it passes** — PASS (6 tests).

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/connection_crypto.py tests/unit/test_connection_crypto.py --fix
ruff format src/dazzle/http/runtime/auth/connection_crypto.py tests/unit/test_connection_crypto.py
git add src/dazzle/http/runtime/auth/connection_crypto.py tests/unit/test_connection_crypto.py
git commit -m "feat(auth): AES-GCM secret-at-rest encryption for connections (Plan 4a)"
```

---

## Task 2: `ConnectionRecord`, the `ConnectionProvider` seam, registry

**Files:**
- Create: `src/dazzle/http/runtime/auth/connections.py`
- Test: `tests/unit/test_connection_provider.py`

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_connection_provider.py
"""ConnectionProvider seam + registry (auth Plan 4a)."""

import pytest

from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    register_provider,
    resolve_provider,
)


def test_asserted_identity_shape() -> None:
    a = AssertedIdentity(email="x@y.test", attributes={"name": "X"}, groups=["admins"])
    assert a.email == "x@y.test" and a.groups == ["admins"]


def test_resolve_unregistered_raises(monkeypatch) -> None:
    # A type/provider with no registered implementation fails loud (4a has none).
    class _Conn:
        type = "oidc"
        provider = "native"

    with pytest.raises(ConnectionError, match="no provider"):
        resolve_provider(_Conn())


def test_register_then_resolve(monkeypatch) -> None:
    class _Conn:
        type = "oidc"
        provider = "native"

    class _Impl:
        def initiate(self, connection, request):  # noqa: ANN001
            return "/redirect"

        def callback(self, connection, request):  # noqa: ANN001
            return AssertedIdentity(email="a@b.test", attributes={}, groups=[])

    register_provider("oidc", "native", _Impl())
    try:
        prov = resolve_provider(_Conn())
        assert prov.initiate(_Conn(), None) == "/redirect"
    finally:
        from dazzle.http.runtime.auth.connections import _PROVIDERS

        _PROVIDERS.pop(("oidc", "native"), None)  # don't leak into other tests
```

- [ ] **Step 2: Run it to verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Create the module**

```python
# src/dazzle/http/runtime/auth/connections.py
"""Per-org enterprise connections + the ConnectionProvider seam (auth Plan 4a).

A ``Connection`` is a framework-owned, org-fenced auth-store record (OIDC/SAML/
SCIM config). Non-secret ``config`` is stored plaintext; secret material is a
single AES-GCM-encrypted blob (see ``connection_crypto``). Domains route to a
connection only when VERIFIED (an unverified claimed domain can't hijack another
org's SSO — spec §5).

The ``ConnectionProvider`` Protocol is the seam: native (authlib OIDC / pysaml2
SAML / SCIM 2.0) vs delegated (a vendor), chosen per connection by ``(type,
provider)``. 4a defines the seam only — ``resolve_provider`` raises until 4b/4c
register the native implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class ConnectionError(RuntimeError):
    """A connection operation cannot proceed (e.g. no provider for type/provider)."""


CONNECTIONS_DDL = """
CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    type TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'native',
    domains TEXT NOT NULL DEFAULT '[]',
    verified_domains TEXT NOT NULL DEFAULT '[]',
    config TEXT NOT NULL DEFAULT '{}',
    encrypted_secret TEXT,
    group_mapping TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CONNECTIONS_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_connections_tenant ON connections(tenant_id)",
)


@dataclass(frozen=True)
class ConnectionRecord:
    id: str
    tenant_id: str
    type: str  # oidc | saml | scim
    provider: str  # native | <vendor>
    domains: list[str]
    verified_domains: list[str]
    config: dict[str, Any]  # non-secret (issuer, client_id, endpoints)
    secrets: dict[str, Any]  # decrypted on read; encrypted at rest
    group_mapping: dict[str, str]  # IdP group/attr → persona (default-deny if unmapped)
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AssertedIdentity:
    """What a SSO provider's ``callback`` asserts after validating the IdP response."""

    email: str
    attributes: dict[str, Any] = field(default_factory=dict)
    groups: list[str] = field(default_factory=list)


@runtime_checkable
class ConnectionProvider(Protocol):
    """The swappable seam — native or delegated, chosen per connection.

    Call sites never know who implements it. SSO providers implement
    ``initiate``/``callback``; SCIM providers expose REST handlers (added in 4c).
    """

    def initiate(self, connection: ConnectionRecord, request: Any) -> str:
        """Return the redirect URL that starts the IdP login (SSO)."""
        ...

    def callback(self, connection: ConnectionRecord, request: Any) -> AssertedIdentity:
        """Validate the IdP response and return the asserted identity (SSO)."""
        ...


# (type, provider) → implementation. 4b/4c register the natives; empty in 4a.
_PROVIDERS: dict[tuple[str, str], ConnectionProvider] = {}


def register_provider(conn_type: str, provider: str, impl: ConnectionProvider) -> None:
    """Register a ConnectionProvider for a (type, provider) pair (called at startup)."""
    _PROVIDERS[(conn_type, provider)] = impl


def resolve_provider(connection: Any) -> ConnectionProvider:
    """Return the provider for ``connection``'s (type, provider), or raise.

    Fail-loud: an unregistered pair raises ``ConnectionError`` — better than a
    silent no-op when a connection references a provider the build doesn't have.
    """
    key = (connection.type, connection.provider)
    impl = _PROVIDERS.get(key)
    if impl is None:
        raise ConnectionError(
            f"no provider registered for connection type={connection.type!r} "
            f"provider={connection.provider!r}"
        )
    return impl
```

- [ ] **Step 4: Run the test to verify it passes** — PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/connections.py tests/unit/test_connection_provider.py --fix
ruff format src/dazzle/http/runtime/auth/connections.py tests/unit/test_connection_provider.py
git add src/dazzle/http/runtime/auth/connections.py tests/unit/test_connection_provider.py
git commit -m "feat(auth): Connection record + ConnectionProvider seam + registry (Plan 4a)"
```

---

## Task 3: Store CRUD (encrypt on write, decrypt on read, verified-domain routing)

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py` (`_init_db` + the connection methods)
- Test: `tests/integration/test_connections_pg.py`

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_connections_pg.py
"""Real-PG proof of the connection substrate (auth Plan 4a)."""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture(autouse=True)
def _conn_key(monkeypatch):
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_conn_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    s = AuthStore(database_url=store_url)
    s._init_db()
    return s


def test_create_stores_secret_encrypted_and_reads_decrypted(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1",
        type="oidc",
        config={"issuer": "https://idp.example", "client_id": "abc"},
        secrets={"client_secret": "TOP-SECRET"},
        domains=["acme.test"],
    )
    # The secret is NOT in the row as plaintext.
    import psycopg as _pg

    with _pg.connect(store_url) as c:
        row = c.execute(
            "SELECT config, encrypted_secret FROM connections WHERE id=%s", (conn.id,)
        ).fetchone()
    assert "TOP-SECRET" not in (row[0] or "") and "TOP-SECRET" not in (row[1] or "")
    assert row[1] is not None  # an encrypted blob is stored
    # Read decrypts.
    got = store.get_connection(conn.id)
    assert got.secrets["client_secret"] == "TOP-SECRET"
    assert got.config["issuer"] == "https://idp.example"


def test_connections_fenced_by_tenant(store_url: str) -> None:
    store = _store(store_url)
    store.create_connection(tenant_id="org-A", type="oidc", config={}, secrets={}, domains=[])
    store.create_connection(tenant_id="org-B", type="scim", config={}, secrets={}, domains=[])
    a = store.get_connections_for_tenant("org-A")
    assert len(a) == 1 and a[0].type == "oidc"


def test_verified_domain_routing_only_matches_verified(store_url: str) -> None:
    store = _store(store_url)
    store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={},
        domains=["acme.test"],  # claimed but NOT verified
    )
    # An unverified claimed domain must NOT route (anti-hijack).
    assert store.get_connection_by_verified_domain("acme.test") is None
    # After verification it routes.
    store.set_connection_verified_domains(
        store.get_connections_for_tenant("org-1")[0].id, ["acme.test"]
    )
    routed = store.get_connection_by_verified_domain("acme.test")
    assert routed is not None and routed.tenant_id == "org-1"
```

- [ ] **Step 2: Run it to verify it fails** — `AttributeError: create_connection`.

- [ ] **Step 3: Add the table to `_init_db`** (after the `invitations` block):

```python
            from dazzle.http.runtime.auth.connections import (
                CONNECTIONS_DDL,
                CONNECTIONS_INDEXES,
            )

            cursor.execute(CONNECTIONS_DDL)
            for _ix in CONNECTIONS_INDEXES:
                cursor.execute(_ix)
```

- [ ] **Step 4: Add the store methods** (after the organization methods). Encrypt the `secrets` dict to one blob on write; decrypt on read:

```python
    def _row_to_connection(self, row: dict[str, Any]) -> "ConnectionRecord":  # noqa: F821
        import json

        from dazzle.http.runtime.auth.connection_crypto import decrypt_secret
        from dazzle.http.runtime.auth.connections import ConnectionRecord

        enc = row.get("encrypted_secret")
        secrets_dict = json.loads(decrypt_secret(enc)) if enc else {}
        return ConnectionRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            type=row["type"],
            provider=row["provider"],
            domains=json.loads(row["domains"]) if row.get("domains") else [],
            verified_domains=json.loads(row["verified_domains"]) if row.get("verified_domains") else [],
            config=json.loads(row["config"]) if row.get("config") else {},
            secrets=secrets_dict,
            group_mapping=json.loads(row["group_mapping"]) if row.get("group_mapping") else {},
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_connection(
        self,
        *,
        tenant_id: str,
        type: str,
        config: dict[str, Any],
        secrets: dict[str, Any],
        domains: list[str],
        provider: str = "native",
        group_mapping: dict[str, str] | None = None,
        status: str = "active",
    ) -> "ConnectionRecord":  # noqa: F821
        """Create a per-org connection; secrets are AES-GCM-encrypted at rest."""
        import json

        from dazzle.http.runtime.auth.connection_crypto import encrypt_secret

        conn_id = secrets_token()  # secrets.token_urlsafe(24)
        now = datetime.now(UTC).isoformat()
        encrypted = encrypt_secret(json.dumps(secrets)) if secrets else None
        self._execute_modify(
            """
            INSERT INTO connections
                (id, tenant_id, type, provider, domains, verified_domains, config,
                 encrypted_secret, group_mapping, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                conn_id, tenant_id, type, provider, json.dumps(domains), json.dumps([]),
                json.dumps(config), encrypted, json.dumps(group_mapping or {}), status, now, now,
            ),
        )
        return self.get_connection(conn_id)  # type: ignore[return-value]

    def get_connection(self, connection_id: str) -> "ConnectionRecord | None":  # noqa: F821
        row = self._execute_one("SELECT * FROM connections WHERE id = %s", (connection_id,))
        return self._row_to_connection(row) if row else None

    def get_connections_for_tenant(self, tenant_id: str) -> list["ConnectionRecord"]:  # noqa: F821
        rows = self._execute(
            "SELECT * FROM connections WHERE tenant_id = %s ORDER BY created_at", (tenant_id,)
        )
        return [self._row_to_connection(r) for r in rows]

    def get_connection_by_verified_domain(self, domain: str) -> "ConnectionRecord | None":  # noqa: F821
        """Route an email domain to its org's connection — VERIFIED domains only.

        Matches against ``verified_domains`` (never the unverified ``domains``
        claim) so org A cannot hijack org B's SSO by claiming its domain.
        """
        d = domain.strip().lower()
        for row in self._execute(
            "SELECT * FROM connections WHERE status = 'active' ORDER BY created_at"
        ):
            import json

            if d in [x.strip().lower() for x in (json.loads(row["verified_domains"] or "[]"))]:
                return self._row_to_connection(row)
        return None

    def set_connection_verified_domains(self, connection_id: str, verified: list[str]) -> None:
        """Set the verified-domain list (the output of a domain-ownership check)."""
        import json

        self._execute_modify(
            "UPDATE connections SET verified_domains = %s, updated_at = %s WHERE id = %s",
            (json.dumps(verified), datetime.now(UTC).isoformat(), connection_id),
        )

    def delete_connection(self, connection_id: str) -> bool:
        return self._execute_modify(
            "DELETE FROM connections WHERE id = %s", (connection_id,)
        ) > 0
```

**NOTES:** (a) `secrets_token()` — use the module's existing `secrets.token_urlsafe(24)` idiom (the file already imports `secrets`; call `secrets.token_urlsafe(24)` directly). (b) `from datetime import UTC, datetime` is already imported at the top of store.py. (c) the `# noqa: F821` forward-ref strings mirror the membership-event methods (the type is imported lazily inside).

- [ ] **Step 5: Run the test to verify it passes** — PASS (all 3).

- [ ] **Step 6: Commit**

```bash
ruff check src/dazzle/http/runtime/auth/store.py tests/integration/test_connections_pg.py --fix
ruff format src/dazzle/http/runtime/auth/store.py tests/integration/test_connections_pg.py
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_connections_pg.py
git commit -m "feat(auth): connection store CRUD — encrypt-at-rest + verified-domain routing (Plan 4a)"
```

---

## Task 4: Alembic `0011_connections` + the `[sso]` extra

**Files:**
- Create: `src/dazzle/http/alembic/versions/0011_connections.py`
- Modify: `pyproject.toml`
- Test: `tests/integration/test_connections_pg.py` (migration-applies test)

- [ ] **Step 1: Migration test** (mirror `0010`'s):

```python
def test_migration_0011_creates_connections(store_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    _store(store_url)
    with psycopg.connect(store_url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS connections")
    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("version_locations", str(fw / "versions"))
    cfg.set_main_option("sqlalchemy.url", store_url.replace("postgresql://", "postgresql+psycopg://"))
    command.stamp(cfg, "0010_invitations")
    command.upgrade(cfg, "0011_connections")
    with psycopg.connect(store_url) as c:
        ok = c.execute("SELECT to_regclass('public.connections') IS NOT NULL").fetchone()[0]
        ver = c.execute("SELECT version_num FROM alembic_version").fetchone()
    assert ok is True and ver[0] == "0011_connections"
```

- [ ] **Step 2: The migration** (mirror `0010_invitations.py`):

```python
# src/dazzle/http/alembic/versions/0011_connections.py
"""Add connections table (auth Plan 4a — per-org enterprise auth connections).

Org-fenced OIDC/SAML/SCIM connection config; secret material is stored in
``encrypted_secret`` (AES-GCM, never plaintext). Idempotent (guards on table
presence); mirrors 0010. No DB FK (auth tables live outside the DSL metadata).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0011_connections"
down_revision = "0010_invitations"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("connections"):
        op.create_table(
            "connections",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("type", sa.Text(), nullable=False),
            sa.Column("provider", sa.Text(), nullable=False, server_default=sa.text("'native'")),
            sa.Column("domains", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("verified_domains", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("config", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("encrypted_secret", sa.Text(), nullable=True),
            sa.Column("group_mapping", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
        )
        op.create_index("ix_connections_tenant", "connections", ["tenant_id"])


def downgrade() -> None:
    if _has_table("connections"):
        op.drop_table("connections")
```

- [ ] **Step 3: `[sso]` extra** — add `"cryptography>=41.0.0",` to the `sso = [...]` list in `pyproject.toml` (enterprise connections need it for secret encryption).

- [ ] **Step 4: Run + commit**

```bash
TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_connections_pg.py -q
git add src/dazzle/http/alembic/versions/0011_connections.py pyproject.toml tests/integration/test_connections_pg.py
git commit -m "feat(auth): alembic 0011 connections + cryptography in [sso] extra (Plan 4a)"
```

---

## Task 5: Verification + adversarial review + ship

- [ ] **Verify:** `mypy src/dazzle`; `python -m pytest tests/ -m "not e2e" -q` (the connection_crypto + provider unit tests; no drift expected — auth-store tables aren't in api-surface baselines; `create_connection` is new, no caller regression); the connections integration suite + the create_membership-caller regression (`_init_db` grew a table).
- [ ] **Adversarial review** (security-sensitive — encryption + org-fencing + anti-hijack):
  - **Encryption at rest:** is the plaintext secret EVER persisted (only `encrypted_secret`)? Is AES-GCM used correctly (random 96-bit nonce per encryption, tag verified on decrypt)? Fail-closed on missing/short/invalid key (no plaintext fallback, no silent empty)? Is the key only read from env, never logged?
  - **Org-fencing:** `get_connections_for_tenant` filters by tenant; can a caller read another org's connection/secrets? (4a is store-level; the org-admin route that gates this is a later slice — note the boundary.)
  - **Anti-hijack (the §5 invariant):** does `get_connection_by_verified_domain` match ONLY `verified_domains`, never the unverified `domains` claim? Could two connections claim the same verified domain (collision → ambiguous routing)? Should verified-domain uniqueness be enforced (note for 4b's verification flow)?
  - **Seam fail-loud:** `resolve_provider` raises (not None / silent) when unregistered?
  - **Secret in errors/repr:** does `ConnectionRecord` (with decrypted `secrets`) risk leaking via logs/`__repr__`/an error? (frozen dataclass default repr includes fields — note if a connection is ever logged.)
  - **Migration parity:** `_init_db` DDL vs `0011` columns match.
- [ ] **Fix findings; CHANGELOG (`### Added`: the Connection substrate + AES-GCM secret-at-rest + ConnectionProvider seam + verified-domain anti-hijack routing; `### Agent Guidance`: set `DAZZLE_CONNECTION_SECRET`; connections are org-fenced, secrets encrypted, domains route only when verified; the seam has no live provider until 4b/4c); `/bump patch`; `/ship`.**

---

## Self-Review

**1. Spec coverage (§5):** `Connection` fenced record (id/tenant_id/type/provider/domains/config/group_mapping/status) ✓; secrets encrypted at rest (AES-GCM) ✓; `ConnectionProvider` seam (Protocol + `AssertedIdentity` + registry) ✓; verified-domain routing anti-hijack ✓. Deferred (acknowledged): NativeOIDCProvider (4b), NativeSCIMProvider (4c), SAML (Plan 5), the org-admin config surface + domain-verification flow (later), JIT provisioning (4b).

**2. Placeholder scan:** code steps are concrete; the one adapt note (`secrets.token_urlsafe(24)` idiom) points at the file's existing convention.

**3. Type consistency:** `ConnectionRecord`/`AssertedIdentity`/`ConnectionProvider`/`register_provider`/`resolve_provider`/`ConnectionError` defined in Task 2 and used by the store (Task 3) + tests; `encrypt_secret`/`decrypt_secret`/`ConnectionSecretError` (Task 1) used by the store; `create_connection`/`get_connection`/`get_connections_for_tenant`/`get_connection_by_verified_domain`/`set_connection_verified_domains` signatures match the integration tests.

**Open risks for execution:** (a) `cryptography` is an extra — the unit/integration tests assume it's installed (it is, via `[signing]` in the dev env); the lazy import keeps core installs clean. (b) the `ConnectionRecord.secrets` decrypted-in-memory + default dataclass `repr` could leak secrets in a log/traceback — the review must flag; consider a custom `repr` that masks `secrets`/`encrypted`. (c) verified-domain uniqueness isn't enforced at the DB level in 4a (the verification flow in a later slice owns that) — `get_connection_by_verified_domain` returns the first match; document.
