# ADR-0055 — Hosting topology is a declared plane (A apex / B provider-subdomain); aliases compose

**Status:** Accepted (2026-08-30)
**Depends on:** [ADR-0036](0036-tenant-hierarchy-data-model.md) (hierarchy + host lens), [ADR-0037](0037-declarative-membership-relation.md) (membership), [ADR-0033](0033-csrf-as-auth-class-disposition.md) (CSRF Origin==Host), [ADR-0003](0003-clean-breaks.md), [ADR-0005](0005-runtime-services.md)
**Does not replace:** ADR-0034 (reserved RLS capstone), ADR-0036, ADR-0037
**Stem:** [`stems/tenancy.md`](https://github.com/manwithacat/dazzle/blob/main/stems/tenancy.md)
**CONOPS:** [`docs/superpowers/specs/2026-08-30-hosting-topology-conops.md`](https://github.com/manwithacat/dazzle/blob/main/docs/superpowers/specs/2026-08-30-hosting-topology-conops.md)
**Issues:** #1657, #1656, #1655 (failure class)

## Context

ADR-0036 named three tenant notions (schema registry, RLS fence, host tenant)
and bound `current_tenant` to the **host** GUC. ADR-0037 declared membership at
the root. Neither named **how HTTP Host relates to a tenant**. The only
implemented relation was B: `TenantResolutionMiddleware` requires Host to be
`{slug}.{domain}` or a canonical host, and `ApexDiscoveryMiddleware` bounced
apex logins onto slug hosts.

`cookie_scope` was then overloaded as a topology switch (#1657). That is the
wrong plane: in code it is only the bounce gate. `set_cookie` does not set
Domain. CyFuture-class apps (everything on www; tenant from membership) inherited
`{slug}.{domain}` routing and lost sessions.

## Decision

### D1 — Four planes; hosting is the fourth declared fact

Isolation, membership, hosting topology, and lens compose. Link-time: membership
root = RLS root = hierarchy root (ADR-0037 D5) **and** `tenant_host.topology` is
present and consistent across a domain. The runtime must not infer A vs B from
`canonical_hosts:` or `cookie_scope:`.

### D2 — Declarative surface: `topology:` on `tenant_host:` (locality)

```dsl
tenant_host:
  topology: apex | provider_subdomain
  domain: example.com
  slug_field: slug
  canonical_hosts: [www.example.com]
  cookie_scope: host
```

`topology:` is **required** when `tenant_host:` is declared (T1, validator-owned).
It is **domain-level**: 2+ kinds sharing `domain:` must agree (Rule 6, same class
as `cookie_scope` / `canonical_hosts` / `super_admin_role`).

Not a top-level `hosting:` / `tenancy: topology:` block — ADR-0037 D3 and
ADR-0036 rejected second places to declare what already lives on `tenant_host:`.

### D3 — Named topologies; leftover tokens stay put; aliases are not a token

| Token | Topology | Host names tenant? |
|-------|----------|--------------------|
| `apex` | A | No. Canonical hosts only. |
| `provider_subdomain` | B | Yes. `{slug}.{domain}`. |

There is **no** `custom_alias` token. Customer hostnames are later rows in
`tenant_host_aliases`, composing with the app's A or B.

Unknown parse tokens (`zzz`, `custom_alias`): parse error. Missing key: T1.
Runtime leftover: mapper `None` / no slug extract — **do not invent B**.

### D4 — `cookie_scope` is not topology

Default `cookie_scope: host`. Apex slug-bounce fires only when
**`topology == provider_subdomain` AND `cookie_scope == apex`**. That bounce is
**not** session sharing until Domain cookies are wired (follow-on). A +
`cookie_scope: apex` is a link-time error (T4).

### D5 — Host never writes the fence except proven-token paths

`TenantResolutionMiddleware` sets `_current_host_tenant_id` only.
`_current_tenant_id` is set by the auth dependency from `partition_root_id`,
JWT bind, or HMAC signing lookup. Signing-on-A uses a `SECURITY DEFINER`
function owned by `dazzle_bypass` (FORCE RLS fences `dazzle_owner`); request
LOGIN stays `dazzle_app`. Do not mint tenant into the HMAC token.

### D6 — Client-supplied tenant is not a resolver

Production resolvers: Host (B), verified alias table (later), membership (A).
Forbidden: `?tenant_id=`, JSON body tenant, `X-Tenant-ID` as authority.

### D7 — Path-prefix tenancy is forbidden

`app.com/acme/...` is not a topology.

## Consequences

- `TenantHostSpec.topology: Literal["apex", "provider_subdomain"] | None`
- Parser closed tokens; T1 owns missing; runtime mappers take `str`
- A requires non-empty `canonical_hosts`; unknown Host on A is 400 (no slug parse)
- `_TenantStateMarker` carries `topology`, `cookie_scope`, `domain`
- Clean break: every in-tree `tenant_host:` declares `topology:`
- Downstream: CyFuture `topology: apex`; slug-host apps `topology: provider_subdomain`

## Failure-modes check

1. **Which failure mode?** Authority leak (wrong tenant fence from Host) and
   silent under-grant (A bounced off its session).
2. **Detector?** RLS fence, `dazzle validate` (T1–T4), `resolve_apex_redirect`
   tests keyed by topology, leftover-honesty case.
3. **Live?** Validate every build; RLS every request.
4. **Traceable to DSL?** `tenant_host.topology` + `cookie_scope` +
   `canonical_hosts`.
5. **Postgres/auth/RLS preserved?** Two tenant-id ContextVars stay separate.
