# SAML IdP-initiated SSO opt-in + assertion replay cache — Design

**Issue:** #1342 (enterprise auth deferred backlog) — the final row: "IdP-initiated SSO opt-in".

## Problem

SAML SSO today is **SP-initiated only**. The ACS refuses any Response without an `InResponseTo` that
matches a one-time, session-stashed AuthnRequest id (`saml_provider.callback`, the "no stashed
request id → refuse" guard + `rejectUnsolicitedResponsesWithInResponseTo=True`). That one-time
session binding is also the replay defense: a captured SP-initiated Response can't be replayed
because the request id is gone from the session after first use.

IdP-initiated (unsolicited) flows have **no** AuthnRequest, hence no `InResponseTo`, hence none of
that replay protection. Some IdPs/portals only do IdP-initiated. Enabling it safely needs an
explicit, per-connection opt-in **and** a replay defense that doesn't rely on the request-id binding.

## Decisions

- **Opt-in is per-connection + operator-set (CLI), default-off.** A `config["allow_idp_initiated"]`
  flag, set via `dazzle auth connection enable-idp-initiated <id>` / `disable-idp-initiated <id>`
  (SAML-only, mirrors `enable-request-signing`). Default off → the current refusal stands unchanged.
  *(In-app toggling by an IT-admin is a clean follow-up: the `/auth/connections` surface is now gated
  on the `manage_connections` capability, so an in-app POST would land there. CLI-only for v1 keeps
  the riskiest feature's surface minimal.)*
- **Replay defense = assertion replay cache, IdP-initiated path only.** SP-initiated is already
  replay-safe (one-time session request id), so the cache runs only on the unsolicited branch — no
  extra DB write on the common login path.

## Replay cache

New table `saml_consumed_assertions`, **dual-written** (`_init_db` + Alembic `0016`, per the
auth-store parity rule [[project_authstore_alembic_parity]]):

```
assertion_id  TEXT PRIMARY KEY    -- the IdP-generated Assertion ID (globally unique)
connection_id TEXT NOT NULL       -- scoping / audit
tenant_id     TEXT                 -- audit
expires_at    TEXT NOT NULL        -- the assertion's NotOnOrAfter (ISO); after this it's invalid anyway
created_at    TEXT NOT NULL
```

Store method `record_consumed_assertion(assertion_id, *, connection_id, tenant_id, expires_at) -> bool`:
- Opportunistically purge expired rows first (`DELETE FROM saml_consumed_assertions WHERE expires_at < now`)
  to bound growth.
- Atomic `INSERT ... ON CONFLICT (assertion_id) DO NOTHING`. Returns **True** if the row was inserted
  (fresh assertion), **False** if it already existed (replay). The atomic insert is the race-safe
  one-time-use check — two concurrent replays can't both win.

## Callback change (`saml_provider.callback`)

Where today an absent `request_id` always refuses, branch on the connection flag:

```python
allow_idp = str((connection.config or {}).get("allow_idp_initiated", "")).lower() == "true"
if not request_id and not allow_idp:
    raise ConnectionError(... "only SP-initiated flows are accepted ...")   # unchanged default
idp_initiated = not request_id  # and allow_idp (by the guard above)

# process_response(request_id=None) on the IdP-initiated path: python3-saml STILL enforces
# signature, audience, recipient, and conditions/NotOnOrAfter; with
# rejectUnsolicitedResponsesWithInResponseTo=True it still REJECTS a replayed SP-response that
# carries an InResponseTo. So the only residual replay vector is a captured genuine IdP-initiated
# Response — closed by the assertion cache below.
auth.process_response(request_id=request_id)   # request_id is None on the IdP-initiated path
... existing errors / authenticated / email checks (unchanged) ...

if idp_initiated:
    assertion_id = auth.get_last_assertion_id()
    if not assertion_id:
        raise ConnectionError(... "IdP-initiated assertion had no id — cannot replay-protect")
    expires_at = auth.get_last_assertion_not_on_or_after() or <now + 10 min ISO>
    store = request.app.state.auth_store
    if not store.record_consumed_assertion(
        assertion_id, connection_id=connection.id,
        tenant_id=connection.tenant_id, expires_at=expires_at,
    ):
        raise ConnectionError(... "SAML assertion already consumed (replay refused)")
```

The store is read from `request.app.state.auth_store` (the callback is request-bound; the ACS route
already uses `request.app.state.auth_store`). Only the IdP-initiated branch touches the store, so
SP-initiated logins are unchanged (no new DB hit).

## Store flag setter

`set_connection_idp_initiated(connection_id, allowed: bool, *, tenant_id=None) -> bool` — mirrors
`enable_connection_request_signing`'s shape: `_load_config_secrets` → set/remove
`config["allow_idp_initiated"]` (`"true"` or pop) → `_write_connection_config_and_secrets`. SAML-only
(raise on non-SAML, like request-signing). Returns True if a row changed.

## CLI

`enable-idp-initiated <id>` / `disable-idp-initiated <id>` (SAML-only, guards mirror
`enable-request-signing`): resolve connection, type-check SAML, call the store setter, print a short
security note ("IdP-initiated accepts unsolicited responses; replay-protected by one-time assertion
consumption — keep this off unless your IdP requires it").

## Files

| File | Change |
|---|---|
| `auth/store.py` | `saml_consumed_assertions` in `_init_db`; `record_consumed_assertion`; `set_connection_idp_initiated` |
| `alembic/versions/0016_saml_consumed_assertions.py` (new) | guarded mirror of the table |
| `auth/saml_provider.py` | `callback` IdP-initiated branch + replay-cache enforcement |
| `cli/auth_connection.py` | `enable-idp-initiated` / `disable-idp-initiated` commands |

## Testing

- **Provider unit** (fake `auth` via `_build_auth`, fake store on `request.app.state`): off →
  unsolicited refused (existing `test_callback_missing_request_id_refuses` stays); on + fresh
  assertion → AssertedIdentity + `record_consumed_assertion` called with the id + NotOnOrAfter; on +
  replayed (store returns False) → ConnectionError; on + no assertion id → ConnectionError;
  SP-initiated (request_id present) → store.record NOT called. Extend `_FakeAuth` with
  `get_last_assertion_id` / `get_last_assertion_not_on_or_after`.
- **Store PG integration** (`-m postgres`): `record_consumed_assertion` fresh→True, duplicate→False,
  expired rows purged; `set_connection_idp_initiated` sets/clears the flag (SAML-only raises).
- **Parity gate** extended: head `0016`, table present after `_init_db` + `alembic upgrade head`.
- **CLI** (`test_auth_connection_cli.py`): enable/disable set/clear the flag; non-SAML → error.

## Non-goals / residual

- No in-app toggle (v1 CLI-only; follow-up on the `manage_connections`-gated surface).
- The replay cache is IdP-initiated-only (SP-initiated already protected).
- `InResponseTo` replay-pinning for SP-initiated is unchanged (already covered).
- A clock-skew note: expiry uses the assertion's `NotOnOrAfter`; python3-saml's own
  conditions/`NotOnOrAfter` validation (with its `allowed_clock_drift`) is the primary time gate —
  the cache only needs to cover that window.

## Model-driven-failure-mode note

This **widens** authority (accepts a flow previously refused), so it's the higher-risk kind of change
— mitigated by: default-off + explicit per-connection opt-in; python3-saml's full
signature/audience/condition validation unchanged; the one-time assertion cache (atomic, race-safe)
closing the only new replay vector; and the operator-only (CLI) opt-in. Runtime behavior traces to
one config flag + one table. The adversarial review must focus here.
