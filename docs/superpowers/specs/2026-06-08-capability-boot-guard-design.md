# Capability Boot Guard (#1344) — Design

**Issue:** #1344 (follow-up to #1342 Phase 1, the capability opt-in model). `enhancement`,
`future` — pulled forward by explicit request (2026-06-08).

## Goal

When a deployment has `connections` rows for a protocol (oidc / saml / scim) whose enterprise
capability is **not active**, the matching routes silently don't mount (SSO/SCIM 404s). That's
**safe** (feature-off, no security hole) but quiet — an operator who upgraded without declaring
`auth.enterprise.{oidc,saml,scim}` in `[capabilities]` gets no signal. Add a boot-time guard
that emits a **loud, actionable ERROR** for each such mismatch.

## Decision: loud-log, not hard-abort

Log a loud `ERROR` at startup; do **not** abort boot. Rationale:
- The mismatch is currently **safe** — aborting would turn a safe-but-quiet state into a hard
  outage (a deploy that has connections but forgot the capability would crash-loop).
- The `lifespan_hooks` registry (v0.81.59) **deliberately swallows hook exceptions** so a dead
  hook can't crash-loop a deploy — a hook physically cannot hard-abort. A true abort would need
  invasive `_lifespan` integration, which we explicitly reject for the reason above.

## Constraint that shapes the design

`AuthStore` reads are **synchronous**, but the DB pool only opens at **lifespan startup** —
*after* subsystem build (where routes mount). So the guard cannot query at build time. It must
run as a lifespan **startup hook**, by which point the pool is open and the query is safe.

## Components

### 1. `AuthStore.connection_type_counts() -> dict[str, int]` (DB read)

Sync: `SELECT type, COUNT(*) FROM connections GROUP BY type` → `{"oidc": 3, "saml": 1, ...}`.
**Defensive:** return `{}` on any failure (missing `connections` table on a fresh/unmigrated
DB, query error). The guard's job is to *warn*, never to break boot, so a query failure is
swallowed to `{}` (and the lifespan registry swallows anything that slips through anyway). The
count drives the "N connection(s)" in the message.

### 2. Pure mapping/warning logic (DB-independent, unit-testable)

In a small pure module (e.g. `src/dazzle/back/runtime/auth/capability_guard.py`):

```python
# connection.type -> the capability that must be active for its routes to mount.
_TYPE_TO_CAPABILITY = {
    "oidc": "auth.enterprise.oidc",
    "saml": "auth.enterprise.saml",
    "scim": "auth.enterprise.scim",
}

def capability_boot_warnings(
    type_counts: Mapping[str, int],
    is_active: Callable[[str], bool],
) -> list[str]:
    """One actionable warning per connection type whose capability isn't active.
    Pure — no DB, no logging — so the mapping + mismatch logic is unit-tested directly."""
    out = []
    for ctype, capability in _TYPE_TO_CAPABILITY.items():
        n = type_counts.get(ctype, 0)
        if n > 0 and not is_active(capability):
            out.append(
                f"{n} {ctype} connection(s) exist but {capability} is not enabled — "
                f"their routes will not mount (SSO/SCIM will 404). Add {capability} to "
                f"[capabilities] in dazzle.toml or run: dazzle capability enable {capability}"
            )
    return out
```

Types not in the map (none today) are ignored — the guard speaks only to the three enterprise
protocols.

### 3. Lifespan startup hook (wires DB + capabilities + logging)

Registered from the auth subsystem (`subsystems/auth.py`) after the enterprise mount, on
`ctx.app` via `register_lifespan_hook(ctx.app, startup=...)`. The hook closes over
`ctx.auth_store` and `ctx.capabilities`:

```python
def _startup() -> None:
    caps = ctx.capabilities
    is_active = caps.is_active if caps is not None else (lambda _cid: False)
    for msg in capability_boot_warnings(ctx.auth_store.connection_type_counts(), is_active):
        logger.error("Capability boot guard: %s", msg)
```

Registered unconditionally (when auth is enabled) — the hook is cheap and the whole point is to
fire when a capability is *absent*, so it can't be gated on capabilities being present. When
`ctx.capabilities is None` (no manifest resolved), `is_active` is `lambda: False`, so any
existing connection type warns — correct (an app with connections but no capability manifest is
exactly the misconfiguration we want to surface).

## Testing

- `tests/unit/test_capability_guard.py` (pure, no DB): the mapping + `capability_boot_warnings`
  — all-active → no warnings; an active type with connections → no warning; an inactive type
  with N connections → one warning naming the type, the count, the capability id, and the
  `dazzle capability enable` remedy; a type with 0 connections → no warning; `capabilities is
  None` path (everything inactive) → warns for every present type; an unknown type → ignored.
- `tests/integration/test_connections_pg.py` (real PG): `connection_type_counts()` returns the
  right per-type counts across mixed connections; returns `{}` cleanly when the table is absent
  (a bare store without `_init_db`) — the don't-break-boot contract.
- (Optional) a lightweight check that the auth subsystem registers a startup hook — but the
  pure + DB tests cover the logic; the wiring is a two-line registration.

## Out of scope

- Hard-abort on mismatch (rejected above).
- Auto-enabling the capability (the guard advises; the operator decides — declaring a
  capability is a deliberate opt-in, #1342's whole premise).
- Non-enterprise connection types (none exist).
