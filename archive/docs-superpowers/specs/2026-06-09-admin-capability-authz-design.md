# Administrative-capability authorization — Design

**Issue:** #1342-adjacent (surfaced while scoping IdP-initiated SSO opt-in). Generalizes the flat
`org_admin_roles` gate into a small, IAM-flavored capability model so a multi-tenant Dazzle app can
distinguish a **tenant business administrator** from a **tenant technical (IT) admin**.

## Problem

The framework's own org-admin surfaces (member management, invitations, enterprise-connection
management) all gate on a single flat list, `org_admin_roles`, via `invitations.may_manage_members`
(set-intersection of the caller's effective in-org roles with that list). That conflates two
distinct responsibility domains: managing *people/business* and managing *SSO connections/technical
integration*. A MAT's IT department and its trust business administrator are different roles; today
anyone who can invite a colleague can also stand up an SSO connection.

This is separate from the app-domain authorization plane (`permit:`/`scope:` → predicate algebra,
`grant_schema` delegation, the `rbac/` verifier), which governs **domain entities**. This design
touches **only** the framework's org-admin surfaces, not that plane.

## Model

The framework names a small, fixed set of **admin capabilities** (the "actions"). The app binds
each to a set of **personas** (the "principals"). A capability check is the set-intersection of the
caller's effective in-org roles (`effective_roles_of(ctx)`) with the capability's persona set;
**default-deny, fail-closed**.

Capabilities shipped:
- **`manage_members`** — invite, list, change roles, remove members (the business administrator).
- **`manage_connections`** — enterprise-connection CRUD, domain claim/verify, secret rotation, and
  connection security toggles incl. IdP-initiated SSO (the IT/technical admin).

The mechanism is a `capability → personas` map, so adding a capability (e.g. `manage_billing`) or
splitting `manage_connections` into a separate `manage_connection_security` later is a config +
small wiring change, never a redesign. We ship exactly the two capabilities.

`CAPABILITIES` is a frozen tuple of the framework-defined capability names; it is the single source
of truth (validation + tests assert against it).

## Manifest shape (`dazzle.toml [auth]`)

```toml
[auth]
org_admin_roles = ["org_admin"]        # unchanged key; now also the DEFAULT for unlisted capabilities

[auth.admin_capabilities]              # new, optional
manage_members     = ["business_admin"]
manage_connections = ["it_admin"]
```

`AuthConfig` (in `core/manifest.py`) gains `admin_capabilities: dict[str, list[str]]`
(default empty). It reads from the manifest loader exactly like `org_admin_roles`.

### Backward-compatibility (load-bearing)

- `[auth.admin_capabilities]` absent → **every** capability resolves to `org_admin_roles`. Existing
  apps behave exactly as today.
- A capability omitted from a present map → falls back to `org_admin_roles` (not empty) — so adding
  `manage_connections = [...]` doesn't silently lock out member management.
- Fail-closed: if a capability's resolved persona set is empty (neither the map nor `org_admin_roles`
  yields anything), `may(...)` returns `False` — nobody is authorized (matches today's
  empty-`org_admin_roles` semantics).

## Runtime — `auth/admin_policy.py` (new)

A frozen value object, pure and unit-testable:

```python
@dataclass(frozen=True)
class AdminPolicy:
    # resolved capability -> frozenset[persona]; every framework capability is present
    _by_capability: dict[str, frozenset[str]]

    @classmethod
    def from_config(cls, *, org_admin_roles, admin_capabilities) -> "AdminPolicy":
        default = frozenset(org_admin_roles or ())
        resolved = {}
        for cap in CAPABILITIES:
            roles = admin_capabilities.get(cap)
            resolved[cap] = frozenset(roles) if roles else default
        return cls(resolved)

    def may(self, capability: str, effective_roles: Iterable[str]) -> bool:
        allowed = self._by_capability.get(capability)
        if not allowed:                      # unknown capability or empty set -> deny (fail-closed)
            return False
        return bool(set(effective_roles) & allowed)

    def roles_for(self, capability: str) -> frozenset[str]:
        return self._by_capability.get(capability, frozenset())
```

Wiring (`subsystems/auth.py`): build once at boot →
`ctx.app.state.admin_policy = AdminPolicy.from_config(org_admin_roles=..., admin_capabilities=...)`.
`app.state.org_admin_roles` stays (other code/tests read it; harmless).

`invitations.may_manage_members(effective_roles, *, org_admin_roles)` is **replaced** by routing
through the policy. To avoid a parallel code path, the route helpers gain a single
`_may(request, capability) -> bool` that reads `request.app.state.admin_policy`. Per ADR-0003
(clean breaks, no shims), `may_manage_members` is removed and its call sites updated in the same
commit; a thin `policy.may("manage_members", roles)` is the replacement. (If a shim proves
necessary for an out-of-tree caller, that's a deviation to flag — default is clean break.)

## Surface re-tiering

| Surface | Capability |
|---|---|
| `member_admin_routes`, `invitation_routes` | `manage_members` |
| `connection_admin_routes` (list, create, add-domain, verify-domain) | **`manage_connections`** |
| IdP-initiated toggle + secret rotation (when/where in-app) | `manage_connections` |

Under default config (no `admin_capabilities`), both capabilities resolve to `org_admin_roles`, so
behavior is **identical to today** — the re-tiering only takes effect once an app declares distinct
persona sets.

## Last-admin guard

`member_admin.py::active_admins(roster, org_admin_roles)` and `would_orphan_org(...)` re-target to
the **`manage_members`** persona set (via `policy.roles_for("manage_members")`) instead of the flat
`org_admin_roles` — "the last person who can manage members" is the correct lockout guard. The
`org_admin_roles: list[str]` parameter becomes the resolved `manage_members` persona set; callers
pass `policy.roles_for("manage_members")`.

## Validation & drift

- `dazzle validate`/lint: persona names in `[auth.admin_capabilities]` not declared as DSL personas
  → a **warning** (typo catches a silent grant-nobody). Non-fatal (personas may be defined outside
  the parsed DSL in some setups); a warning is the right strength.
- Unit drift gate: assert every name in `CAPABILITIES` is consumed by at least one route/guard
  (no orphan capability), and that `AdminPolicy` defaults to `org_admin_roles` + fails closed.

## Testing

- `tests/unit/test_admin_policy.py` (pure): default-deny; `org_admin_roles` fallback when map
  absent / capability omitted; explicit map honored; fail-closed on empty + unknown capability;
  `roles_for` returns the resolved set.
- `tests/integration/test_connection_admin_routes.py` + `tests/unit/test_member_admin.py` (extend):
  `manage_connections` gates the connection surface, `manage_members` the member surface; a
  **back-compat test** — only `org_admin_roles` set → both surfaces authorize the org_admin role
  exactly as before; a **separation test** — `it_admin` may create connections but not invite, and
  `business_admin` vice-versa.
- Manifest-load test: `[auth.admin_capabilities]` parses into `AuthConfig.admin_capabilities`.

## Out of scope (deliberate, YAGNI — full IAM is 6+ months out)

- Policy documents, explicit deny-overrides, wildcards, conditions.
- Per-user (non-role) grants.
- App-defined admin action namespaces.
- Any change to the app-domain `permit:`/`scope:`/`grant_schema` plane.

## Model-driven-failure-mode note (per CLAUDE.md review rule)

This is a thin, config-bound authorization layer, not a new escape hatch. (1) It risks the
"declarative authz drifts from runtime" mode least — it *narrows* authority (default-deny,
fail-closed) rather than widening it. (2) The validation gate (unknown-persona warning) + unit drift
gate catch misconfiguration. (3) Those gates are live in the normal `validate`/test workflow. (4) A
competent engineer traces any allow/deny to two manifest keys (`org_admin_roles`,
`admin_capabilities`) + the `CAPABILITIES` tuple. (5) It preserves auth semantics — personas remain
the principal vocabulary; no logic moves into side code. Not marketed as a new safe pattern beyond
this bounded use.
