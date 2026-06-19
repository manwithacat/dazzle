# Multi-Tenant Hosts (`tenant_host:`)

The `tenant_host:` entity sub-block (#1289) auto-mounts a Host-header
tenant routing stack: subdomain → entity lookup, history-table 301/410
redirects, and (in follow-up slices) a cross-tenant session guard plus
`__Host-` / `__Secure-` cookie naming. Apps that don't use it are
unaffected.

## When to use it

When your app routes by subdomain — `acme.example.com`,
`westwood.example.com` — and you want the framework to handle
resolution, caching, redirect history, and cookie scoping.

## Minimum example

```dsl
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
```

Boot the app and any request to `<slug>.example.com` will resolve through
the framework's tenant middleware. `request.state.tenant` carries a typed
`ResolvedTenant` (kind, id, slug, name) for the matching row, or is
`None` for canonical-host requests.

## Full surface

| Sub-field | Default | Meaning |
|---|---|---|
| `domain:` (required) | — | the base host suffix (e.g. `aegismark.ai`) |
| `slug_field:` (required) | — | name of the `slug:` field on this entity |
| `canonical_hosts:` | `[]` | host(s) that pass through with `request.state.tenant = None` (admin / marketing on apex) |
| `cookie_scope:` | `host` | `host` or `apex`; drives cookie naming |
| `super_admin_role:` | `super_admin` | role allowed to hold the apex cookie |
| `history_entity:` | _none_ | entity tracking renamed slugs (`old_slug`, `new_slug`, `expires_at` fields) |
| `not_found_template:` | framework default | dotted-path callable (`module:symbol`) returning 404 HTML |
| `expired_template:` | framework default | dotted-path callable (`module:symbol`) returning 410 HTML |
| `order:` | lexical | required iff 2+ entities share a `domain:` |
| `membership_gated:` | `true` | `false` decouples host resolution from membership-gated login (#1418): the host + `current_tenant` lens work without the enterprise-auth membership table — a host-pinned login with no membership proceeds (the app self-authorizes) instead of 403. Leave `true` for the membership-gated model. |

See the design spec at
[`docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md`](../superpowers/specs/2026-05-28-tenant-host-keyword-design.md)
for the full truth table and lifecycle.

## Cookies (planned)

- Non-`tenant_host:` apps: `dazzle_session` cookie unchanged.
- `tenant_host:` apps will switch to `__Host-<app>_session` for tenant
  sessions and `__Secure-<app>_admin` for canonical-host super-admin
  sessions, where `<app>` is the `app <name>` declaration lowercased
  with non-alphanumerics collapsed to underscore. The naming helpers
  ship in `dazzle.back.runtime.tenant.cookies`; the login-flow
  integration is staged for a follow-up.

## Cache busting

The framework keeps an in-process LRU cache for tenant resolution
results (positive hits + a `NEGATIVE` sentinel for memoised
cache-misses). For raw-SQL renames, migration fixups, or admin
tooling that bypasses `Repository`, call:

```python
import dazzle.tenant
dazzle.tenant.bust("renamed-slug")
```

The framework also auto-busts on `Repository.update` for any
slug-field change on a `tenant_host:` entity — that hook lands in a
follow-up; today you should call `bust()` explicitly after each
rename.

## Validate-time checks

`dazzle validate` rejects:

1. `slug_field` pointing at a non-`slug:`-typed field
2. A malformed `domain:`
3. Multiple entities on one `domain:` without distinct `order: N` values
4. `history_entity:` pointing at an entity that doesn't exist
5. A dotted-path template that can't be imported
6. Inconsistent `cookie_scope:` / `super_admin_role:` / `canonical_hosts:` across entities sharing a `domain:`

It warns on:

- The full lookup order across multi-entity domains (helper output)
- Multi-domain configurations (slugs are not unique across domains)

## Cross-tenant guard

`dazzle.back.runtime.tenant.guard.check_cross_tenant()` enforces the
truth table from the spec: tenant-bound cookies can't be reused on a
different tenant's host, and apex super-admin cookies can't be
presented on a tenant host without the super-admin role. The
auth-dependency integration is staged for a follow-up; today the guard
is callable directly from project code.

## See Also

- [Project Layout](project-layout.md) — where `tenant_host:` fits with
  `pipeline/`, `routes/`, and the project post-build hook (#1290)
- [`slug:` field primitive](grammar.md#field-types) — the field type
  `tenant_host.slug_field` must reference (shipped in #1288)
- Issue [#1289](https://github.com/manwithacat/dazzle/issues/1289) —
  the design discussion
