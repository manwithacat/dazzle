# Stem: Tenancy is four planes

## Claim

Multi-tenancy is **four planes** that compose and must not collapse:
**isolation** (how rows are fenced), **membership** (which identities may
enter a tenant-root), **hosting topology** (how HTTP Host names a place —
or does not), and **lens** (`current_tenant` / `dazzle.host_tenant_id`
inside the fence). Hosting is a **declared** fact
(`tenant_host.topology`: `apex` | `provider_subdomain`), never inferred
from `canonical_hosts:` or `cookie_scope:`. Customer domains are aliases
of an existing tenant, not a third topology token. Single-tenant is the
default.

## Reconstruct

- Isolation: `none` | `shared_schema` (RLS `dazzle.tenant_id`) |
  schema-per-tenant (`search_path`). Not hosting.
- Membership: framework `memberships` + `membership:` on the **root
  kind** (ADR-0037). `partition_root_id` is the fence key (#1463).
- Hosting: `none` | `apex` (A) | `provider_subdomain` (B). Host, verified
  alias table (composing), or membership — never `?tenant_id=` / body /
  `X-Tenant-ID`.
- Lens ≠ fence: two tenant-id ContextVars (`_current_host_tenant_id` vs
  `_current_tenant_id`). Schema search_path and user-attr GUCs are other
  isolation knobs.
- Cookies default `__Host-*`. `cookie_scope: apex` is B-only bounce
  intent; Domain cookies are a separate wiring step.
- Custom domains alias an existing tenant id; they are not
  `topology: custom_alias`.
- Domain-join email TXT is identity onboarding, not HTTP routing.
- Jobs/tests declare tenant; reset preserves tenant-root.
- Leftover topology tokens: parse error / T1 / mapper `None` — do not
  invent B.

## Not this

- Treating `tenant_host:` as “the multi-tenant feature” (collapses 2–4
  into B).
- Inferring A vs B from `canonical_hosts:` or `cookie_scope:` (#1657
  class).
- Folding `dazzle.host_tenant_id` into the RLS fence (#1656 class if
  generalised).
- Path-prefix tenancy (`/acme/...`) as a fourth host model.
- Client-named tenant (`X-Tenant-ID`, query, body) as a resolver.
- Top-level `hosting:` / `tenancy: topology:` (rejected: locality; see
  ADR-0055 D2).
- Exclusive `topology: custom_alias` (forbids B slug hosts + customer
  hostname on one app).
- Silent 302 across hosts with `__Host-*` cookies advertised as
  “session sharing.”
- Quick reuse of detached slugs/hostnames (dangling DNS / takeover).
- Growing `DATABASE_PER_TENANT` or implementing DD-001.

## Expressions

- ADR-0055; ADR-0036, ADR-0037, ADR-0033, ADR-0005, ADR-0003, ADR-0052
- `docs/superpowers/specs/2026-08-30-hosting-topology-conops.md`
- `docs/reference/tenant-hosts.md`, `docs/reference/verified-domain-join.md`
- `src/dazzle/http/runtime/tenant/{middleware,apex_middleware,cookies,guard,resolver}.py`
- `src/dazzle/http/runtime/tenant_isolation.py`
- `src/dazzle/http/runtime/auth/apex_discovery.py`
- `src/dazzle/core/ir/domain.py` `TenantHostSpec`; `src/dazzle/core/validation/tenancy.py`
- `src/dazzle/signing/routes.py` `_signing_rls_tenant` (#1656)
- `src/dazzle/http/runtime/test_routes.py` `_entity_is_tenant_root` (#1655)
- Fixtures: `fixtures/tenant_hierarchy`; example: `examples/domain_join_co`
- CHANGELOG v0.112.1–.4 (#1656, #1655, #1657, ADR-0055)
