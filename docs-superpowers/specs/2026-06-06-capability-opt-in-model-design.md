# Capability opt-in model — design

**Date:** 2026-06-06
**Issue:** #1342 (Enterprise auth OIDC/SAML/SCIM — deferred backlog)
**Status:** Approved design, ready for implementation planning

## Problem

Dazzle shipped a full enterprise-auth stack (v0.81.28→57: OIDC/SAML/SCIM
connections, domain verification, doctor, operator CLI, in-app org-admin surface,
secret/key rotation). Connections are **runtime data, not DSL**, so they don't
clutter the grammar — good. But the *gate* that decides whether the enterprise
HTTP surface mounts is **dependency presence**, not app intent:

- `subsystems/auth.py:244` — `enterprise_enabled = find_spec("authlib")` → if the
  `[sso]` extra is installed, enterprise SSO routes mount on **every** app.
- `find_spec("onelogin")` → SAML routes likewise.
- SCIM routes mount **unconditionally** (`auth.py:301-307`).

So a simple app in a shared virtualenv where `[sso]` happens to be present sprouts
enterprise routes, the `/auth/connections` org-admin surface, and the agent/docs
keep presenting enterprise auth to authors who don't need it. The goal:
**enterprise features (and other heavy/advanced features) must be opt-in *as
required*, per app — invisible to a greenfield user until declared.**

Decided scope (from brainstorming):
- Build the **opt-in capability model first**; the 13 backlog items in #1342 are
  downstream and inherit the gate.
- Gate depth = **runtime + cognition**: routes, the org-admin surface, **and**
  agent/docs surfacing. Framework tables stay (invisible — gating schema adds
  Alembic complexity for no user-visible gain).
- A **general capability registry**, not an auth-specific flag — enterprise auth
  is consumer #1; compliance-evidence, multi-org UX, etc. adopt the same pattern.

## The model

Two orthogonal gates, resolved at boot:

1. **Available** (deployment fact) — can this runtime *do* it? Is the pip extra
   present (`find_spec`)? This is today's only gate.
2. **Requested** (app intent) — does this app *declare* it needs the capability?
   **New.** Lives in `dazzle.toml`:

   ```toml
   [capabilities]
   enabled = ["auth.enterprise.oidc", "auth.enterprise.scim"]
   ```

A capability is **active** iff `requested ∧ available`. Default `enabled = []` → a
greenfield app activates nothing.

### Registry (source of truth)

Each capability self-describes; subsystems register theirs at import time.

```python
Capability(
    id="auth.enterprise.saml",
    label="Enterprise SAML SSO",
    required_extras=["saml"],          # pip: dazzle-dsl[saml]
    remediation="pip install 'dazzle-dsl[saml]'  # needs native libxmlsec1",
)
```

Lives in `src/dazzle/core/capabilities/` (the `Capability` dataclass + a process
registry). The registry is the **allowlist**: an unknown id in the manifest is a
`dazzle validate` error with did-you-mean suggestions.

### Boot resolution

Resolution produces three sets:

- **active** = requested ∧ available → wire it up.
- **requested-but-unavailable** → **hard boot error** with the capability's exact
  `remediation` string (you declared it; it's not installed → fail loud, per the
  auth north-star). Not a silent skip.
- **available-but-not-requested** → dormant: no routes, no surfacing. This is the
  leak we close — an incidentally-installed extra does nothing until declared.

`SubsystemContext` carries the resolved set as `.capabilities`, exposing
`capabilities.active(id) -> bool`.

## Consumer #1 — enterprise auth (runtime gating)

Three capability ids mirror the existing extras split:

| Capability id | Required extra | Gates |
|---|---|---|
| `auth.enterprise.oidc` | `[sso]` (authlib, dnspython) | enterprise SSO routes + native OIDC provider |
| `auth.enterprise.saml` | `[saml]` (python3-saml/libxmlsec1) | SAML routes + native SAML provider |
| `auth.enterprise.scim` | `[sso]` | SCIM routes |

Refactor in `subsystems/auth.py` (replaces the `find_spec`-only gates at 236-307):

```python
caps = ctx.capabilities
if caps.active("auth.enterprise.oidc"):
    register_native_oidc(); ctx.app.include_router(create_enterprise_sso_routes())
if caps.active("auth.enterprise.saml"):
    register_native_saml(); ctx.app.include_router(create_saml_routes())
if caps.active("auth.enterprise.scim"):
    ctx.app.include_router(create_scim_routes())   # no longer unconditional
```

- `caps.active(id)` encapsulates `requested ∧ available` (the `find_spec` checks
  move *into* the registry).
- `SessionMiddleware` keys off "any enterprise capability active" instead of
  `configured or enterprise_enabled or saml_enabled`.
- The org-admin surface (`connection_admin_routes.py`, `/auth/connections`) gates
  on **any** `auth.enterprise.*` active — no enterprise capability, no surface.

### Migration safety (the one real hazard)

Switching from extra-presence to declared-intent is a clean break. A deployment
with existing `Connection` rows but no declared capability would silently stop
serving SSO. The auth subsystem adds a **boot guard**: if connection rows exist
for a protocol whose capability isn't active, **fail loud** — *"N OIDC connections
exist but `auth.enterprise.oidc` isn't enabled; add it to `[capabilities]` or run
`dazzle capability enable auth.enterprise.oidc`."* Converts a silent regression
into an actionable one (itself a consumer of the model).

Backward-compat: per project policy, clean break — the one downstream consumer
adds the capability line (or runs the enable command); documented in CHANGELOG
`### Changed` with the exact migration step.

## Cognition gating (the "don't overwhelm" core)

Governing principle: **declaring a capability flips its guidance from *pull-only*
to *push*.**

- **Not declared → latent.** Never *proactively* raised. Still **discoverable on
  demand** — `dazzle capability list` shows every available capability (incl.
  dormant), and a direct KG question ("how do I set up SAML?") still answers. You
  can't be overwhelmed by what's never pushed, but you can't get stuck either.
- **Declared → active.** Its guidance/examples/doctor/next-steps become eligible
  for proactive surfacing.

Mechanism — a `capability:` tag on surfaced guidance + one filter rule:

- **KG / `knowledge` tool**: enterprise-auth nodes tagged `capability:
  auth.enterprise.*`. *Proactive* surfacing (bootstrap relevance, lint hints)
  filters out gated nodes unless active; *direct* queries still return them.
- **Capability Discovery** (existing contextual-relevance mechanism,
  `project_capability_discovery`): gains a `gated_by` field; gated entries are
  suppressed from proactive lint/bootstrap suggestions until active.
- **`bootstrap`**: surfaces only active + ungated capabilities — **with one
  exception** tied to the north-star: if the SPEC/requirement explicitly names the
  intent ("staff sign in via Okta", "SCIM provisioning"), bootstrap *recognises
  the binary requirement* and suggests `dazzle capability enable
  auth.enterprise.oidc` rather than silently dropping it.
  Requirement-detected → *suggest declaring*; declared → *push*; neither →
  *silent*.
- **Docs**: static site, not per-app — out of scope for gating. `enterprise-sso.md`
  stays as the pull-reference; gets a "this is an opt-in capability — enable
  with…" header.

## Ergonomics & validation

**`dazzle capability` CLI** (binary-requirement→config + runbook embodiment):

- `list` — every capability with status: `active` / `dormant` (available, not
  declared) / `declared-but-unavailable` (with remediation).
- `enable <id>` — writes the `[capabilities]` entry **and prints the runbook**: the
  pip extra to install, the IdP app + redirect/ACS URL, the
  `DAZZLE_CONNECTION_SECRET` step, the `dazzle auth connection create…` follow-up.
- `disable <id>`, `status`.

**`dazzle validate`** — unknown capability id → error w/ did-you-mean; reports
declared-but-unavailable.

## How #1342's backlog slots in

Each of the 13 deferred items becomes "a feature within an already-gated
capability" — inheriting opt-in for free:

| Backlog group | Capability |
|---|---|
| SAML SLO, encrypted assertions, SP-signed AuthnRequests, IdP-metadata import, SP-metadata endpoint, IdP-initiated opt-in | `auth.enterprise.saml` |
| SCIM `/Groups`, `/Schemas`+`/ResourceTypes` | `auth.enterprise.scim` |
| `connection doctor --probe`, in-app connection *creation* | tooling under the relevant capability |
| **CITEXT `users.email` (M2)** | **none — unconditional** (correctness/safety, not a feature; ships independent of any capability) |

The model is the prerequisite that lets the backlog grow without overwhelming
greenfield users.

## Phasing

The spec documents all three phases; the **first implementation plan is Phase 1**.

- **Phase 1 — foundation** (self-contained, shippable; closes the route/surface
  leak): registry + `Capability` model + manifest `[capabilities]` + `validate`
  integration + boot resolution + auth runtime gating (the `auth.py` refactor,
  SCIM no longer unconditional, org-admin surface gating) + the
  existing-connections boot guard + `dazzle capability` CLI + the `enterprise-sso.md`
  opt-in header.
- **Phase 2 — cognition**: KG `capability:` tag + push/pull proactive filter +
  Capability Discovery `gated_by` + bootstrap requirement-detection.
- **Phase 3+** — the #1342 backlog items, each under its gated capability, as
  required.

## Testing

- **Resolution matrix**: requested × available → {active, requested-but-unavailable
  (loud error), dormant}.
- **Route-mount gating**: undeclared → routes not registered; declared+available →
  mount; declared+unavailable → loud boot error.
- **Existing-connections boot guard**: connection rows for an undeclared protocol →
  actionable boot failure.
- **Validation**: unknown capability id → error with suggestions.
- **Registry contract**: every registered capability declares `required_extras` +
  `remediation` (drift-style test).
- **(Phase 2)** gated KG node suppressed from proactive surfacing but returned on
  direct query.

## Non-goals / explicitly deferred

- Gating framework schema (connection/SCIM tables) on capability — invisible
  already; conditional Alembic not worth it.
- DSL grammar for capabilities — connections + capabilities are config/runtime, not
  DSL (keeps the grammar clean; the user's core concern).
- Named tiers / bundles — rejected in favour of granular per-capability ("as
  required").
- Per-app *dynamic* (data-driven) mounting — routes mount at boot from the declared
  set; "inert until a connection exists" remains the runtime behaviour beneath the
  intent gate.
