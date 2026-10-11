# `tenant_host:` Entity Keyword — Design Spec

**Issue:** [#1289](https://github.com/manwithacat/dazzle/issues/1289)
**Date:** 2026-05-28
**Status:** Design approved; ready for implementation plan
**Pairs with:** [#1288](https://github.com/manwithacat/dazzle/issues/1288) (`slug:` field primitive — Phase 1 shipped v0.80.11), [#1290](https://github.com/manwithacat/dazzle/issues/1290) (project post-build hook — shipped v0.80.10)

## Problem

Multi-tenant Dazzle apps that route by HTTP `Host` header all reimplement the same five-piece machinery: resolution middleware, canonical-host pass-through, 301/410 history redirects, cross-tenant session guard, and host-vs-apex cookie scoping. AegisMark phase 1 has shipped all five project-side in `pipeline/tenant/{middleware,resolver,cache,guard,cookies}.py` (Heroku v704, behind `TENANT_HOSTS_ENABLED=false`). We want a `tenant_host:` per-entity DSL keyword that auto-mounts the whole stack and lets AegisMark delete those modules.

## Scope decision

**Full proof-of-shape** in this design — resolution + cache + history-redirect + cross-tenant guard + cookie wiring all land. Staged across seven slices (see Build Sequence).

Note: full proof-of-shape includes 301/410 redirects on renamed/expired slugs, which requires a slug-history table. #1288 only shipped Phase 1 + validator (no history primitive in the slug type yet). This spec accepts a project-provided history entity referenced via `history_entity:` — same shape as the eventual `history:` sub-field on `slug:` when #1288 Phase 3 lands.

## DSL surface

```dsl
entity Trust:
  id: uuid pk
  slug: slug required unique
  name: str(120) required

  tenant_host:
    domain: aegismark.ai
    slug_field: slug
    canonical_hosts: [www.aegismark.ai, aegismark.ai]
    cookie_scope: host
    super_admin_role: super_admin
    history_entity: TenantSlugHistory
    not_found_template: pipeline.tenant.templates:render_not_found
    expired_template: pipeline.tenant.templates:render_expired
    order: 1            # required iff 2+ entities share domain:

entity School:
  id: uuid pk
  slug: slug required unique
  trust: ref Trust required

  tenant_host:
    domain: aegismark.ai
    slug_field: slug
    history_entity: TenantSlugHistory
    order: 2
```

All sub-fields except `domain:` and `slug_field:` are optional. Defaults:

| Sub-field | Default |
|---|---|
| `canonical_hosts` | `[]` (only the bare tenant subdomain is recognised) |
| `cookie_scope` | `"host"` |
| `super_admin_role` | `"super_admin"` |
| `history_entity` | `null` (no 301/410 path) |
| `not_found_template` | framework default 404 |
| `expired_template` | framework default 410 |
| `order` | lexical position (only allowed when single entity per domain) |

## IR shape

New frozen Pydantic model in `src/dazzle/core/ir/domain.py`:

```python
class TenantHostSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain: str
    slug_field: str
    canonical_hosts: list[str] = []
    cookie_scope: Literal["host", "apex"] = "host"
    super_admin_role: str = "super_admin"
    history_entity: str | None = None
    not_found_template: str | None = None
    expired_template: str | None = None
    order: int | None = None
```

Wired on `EntitySpec` as an optional field:

```python
class EntitySpec(BaseModel):
    ...
    tenant_host: TenantHostSpec | None = None
```

## Parser changes

- New lexer keyword token: `TENANT_HOST = "tenant_host"`.
- New entity-block parser dispatcher entry, alongside `permit:`, `temporal:`, etc., handling the indented sub-field block.
- Grammar update in `docs/reference/grammar.md` (EBNF + the entity-keyword listing).
- Drift baseline regen for `docs/api-surface/{dsl-constructs,ir-types}.txt`.

## Validator pass (lint-level rules)

Hard errors (block `dazzle validate`):

1. `slug_field` must name a field on the same entity with type `slug` (FieldTypeKind.SLUG)
2. `domain` must be a syntactically valid host (basic dotted check)
3. If 2+ entities declare the same `domain:`, each must carry an explicit `order: N` with distinct integer values
4. `history_entity`, if set, must reference an existing entity carrying at least `old_slug: slug` and `expires_at: datetime` fields
5. `not_found_template` / `expired_template` dotted paths must be importable at validate time and resolve to callables — same convention as `signing_validator:` (#1283)
6. When 2+ entities share a `domain:`, the following sub-fields must be either identical across all entries or only declared once: `canonical_hosts`, `cookie_scope`, `super_admin_role`. They describe domain-level rather than entity-level state; inconsistent values are ambiguous.

Info-level warnings:

6. When 2+ entities share a `domain:`, print the resolution order to the developer so it's visible
7. Cross-domain slug collision: if the same slug value can resolve under two different domains, warn

## Runtime: request lifecycle

1. HTTP request lands.
2. `TenantResolutionMiddleware.dispatch()`:
   - Parse `Host`, lowercase, strip port.
   - If host is in `canonical_hosts` of any `tenant_host:` block → set `request.state.tenant = None`, call_next (admin / marketing on apex).
   - If host does not end with any registered `base_suffix` → 400 Bad Host.
   - `slug = host[: -len(base_suffix)]`.
   - If slug empty or fails the #1288 slug validator (reserved set, format) → render `not_found_template` (or framework default).
   - Probe the cache. `NEGATIVE` sentinel → 404. Hit → use cached result.
   - On cache miss: walk `tenant_host_entities` in lexical / `order:` sequence, run a system-context Repository lookup `find_by(entity, slug_field, slug)` for each. First match wins.
   - If no entity matches AND `history_entity` is set, look up the history table:
     - Active entry (`expires_at > now()`) → `HistoryHit(old_slug, new_slug)` → 301 to `<new_slug>.<domain>`.
     - Expired entry → `ExpiredHistoryHit(old_slug, new_slug)` → 410 (`expired_template` or default).
   - Cache the result (positive or `NEGATIVE`).
   - On `ResolvedTenant`: attach to `request.state.tenant` and call_next.
3. Auth-dependency hook (`CrossTenantGuard.check`):
   - Reads `request.state.tenant` and the authenticated user.
   - Inspects which cookie is present (`__Host-<app>_session` vs `__Secure-<app>_admin`).
   - Applies the truth table:

     | Cookie | Tenant | User role | Result |
     |---|---|---|---|
     | `__Host-` | matches state | any | pass |
     | `__Host-` | mismatch | any | 403 CrossTenantForbidden |
     | `__Host-` | None (apex) | any | 403 HostCookieMissingTenant |
     | `__Secure-` | any | == `super_admin_role` | pass |
     | `__Secure-` | any | != `super_admin_role` | 403 ApexCookieNotSuperAdmin |

## Error responses

| Condition | Status | Body |
|---|---|---|
| Missing / malformed `Host` | 400 | plain text "Bad Host" |
| Host outside any registered `domain:` base suffix | 400 | plain text "Bad Host" |
| Slug missing, reserved, or format-invalid | 404 | `not_found_template` or framework default |
| No tenant + no history hit | 404 | `not_found_template` or framework default |
| Active history hit | 301 | `Location: <new_slug>.<domain>` |
| Expired history hit | 410 | `expired_template` or framework default |
| Cross-tenant cookie violation | 403 | plain text + log entry |
| Repository lookup raises (DB unavailable) | 502 | plain text "Tenant lookup failed"; cache NOT poisoned with NEGATIVE |

## Cache contract

- New `dazzle.http.runtime.tenant.cache.TenantCache` — module-level singleton, configurable via env or `app_init.py`.
- Defaults: `max_entries = 1024`, `ttl_seconds = 60`.
- Stores positive `ResolvedTenant | HistoryHit | ExpiredHistoryHit` and a `NEGATIVE` sentinel for cache-miss memoisation.
- Auto-bust: the framework wraps `Repository.update()` (post-commit) for any entity carrying `tenant_host:`. When the row's slug-field value changes, `cache.bust(old_slug)` runs, and `cache.bust(new_slug)` runs to clear any negative entry on the new value.
- Manual API: `dazzle.tenant.bust(slug: str) -> None` exposed at the top-level package for raw-SQL renames, migration fixups, and admin tooling.

## Cookie wiring

- Apps without any `tenant_host:` block: zero change. Existing `dazzle_session` cookie name preserved.
- Apps with at least one `tenant_host:` block: the session cookie switches to a convention-based name:
  - `__Host-<app>_session` — set on every tenant-bound login; `Path=/`, `SameSite=Lax`, no `Domain` attribute (host-locked).
  - `__Secure-<app>_admin` — set when the login resolves on a canonical host AND the user has `super_admin_role`; `Domain=.<base_domain>`, `Path=/admin`, `SameSite=Strict`.
- `<app>` comes from the `app <name>` DSL declaration, lowercased and with any non-`[a-z0-9]` character collapsed to underscore (e.g. `app aegismark-prod` → `aegismark_prod`). Documented in the new reference page so naming is deterministic and reviewable.
- Login-flow decision tree (in the framework's password / SSO login routes):
  1. If request `Host` ∈ any `tenant_host.canonical_hosts` AND user has `super_admin_role` → set `__Secure-<app>_admin`.
  2. Otherwise → set `__Host-<app>_session`.
- Logout clears both cookies if both exist.

## Templates

Both `not_found_template:` and `expired_template:` take a dotted-path callable — the same convention as `signing_validator:` from #1283.

```python
# pipeline/tenant/templates.py
def render_not_found(host: str) -> str:
    return f"<!doctype html><html><body><h1>Tenant not found</h1>...</body></html>"

def render_expired(old_slug: str, new_slug: str, ttl_remaining_days: int) -> str:
    return f"<!doctype html>... moved to {new_slug}; this link expired ..."
```

Framework defaults ship in `dazzle.http.runtime.tenant.templates` and produce minimal branded pages using the app name from the IR. Projects override per-block via the dotted-path sub-fields.

## Module layout

New package: `src/dazzle/http/runtime/tenant/`

| File | Purpose |
|---|---|
| `middleware.py` | `TenantResolutionMiddleware` (BaseHTTPMiddleware) |
| `resolver.py` | `ResolvedTenant`, `HistoryHit`, `ExpiredHistoryHit`, lookup chain |
| `cache.py` | `TenantCache` with LRU + ttl + bust API |
| `guard.py` | `CrossTenantGuard` truth-table check |
| `cookies.py` | name builders + set/get/clear helpers |
| `templates.py` | framework default `render_not_found` / `render_expired` |

## Testing

| Layer | Tests |
|---|---|
| Parser | tenant_host block roundtrip; each sub-field type-checked; rejection cases for unknown sub-fields |
| Validator | one test per hard-error rule (slug_field mistyped, missing domain, missing order on multi-entity, etc.) |
| Cache | positive set/get, NEGATIVE memoisation, LRU eviction, ttl expiry, bust pre/post commit |
| Resolver | lookup chain across two entities, history hit (active + expired), missing-everywhere → NEGATIVE |
| Guard | every truth-table row, plus the "no cookie at all" fall-through |
| Cookies | name construction from app name + scope; set/get/clear correctness; logout clears both |
| Integration | end-to-end through `TestClient` with seeded `Trust` + `School` + history rows; assertions on 200 / 301 / 404 / 410 / 403 / 400 |
| Lift | AegisMark's existing tenant-middleware tests where the public contract matches |

## Drift gates

- `docs/api-surface/ir-types.txt` — regen to include `TenantHostSpec` + the new `EntitySpec.tenant_host` field
- `docs/api-surface/dsl-constructs.txt` — regen to include the parser entry
- `tests/unit/test_docs_drift.py` — `tenant_host` listed in the CLAUDE.md "Constructs" line

## Migration & backward compatibility

- Apps without any `tenant_host:` block are unaffected.
- Apps adopting `tenant_host:` see their session cookie name change on first deploy; users get logged out once.
- This matches AegisMark's existing feature-flagged rollout precedent (`TENANT_HOSTS_ENABLED=false` before pin-bump, then flipped after).
- Documented in CHANGELOG `Agent Guidance` plus a new `docs/reference/tenant-hosts.md` reference page.

## AegisMark deletion targets after pin-bump

| File | After this ship |
|---|---|
| `pipeline/tenant/middleware.py` | delete |
| `pipeline/tenant/resolver.py` | delete |
| `pipeline/tenant/cache.py` | delete |
| `pipeline/tenant/guard.py` | delete (framework guard supersedes) |
| `pipeline/tenant/cookies.py` | delete (framework cookies supersede) |
| `pipeline/tenant/reserved_slugs.py` | keep (project policy data, per #1288 out-of-scope clause) |
| `pipeline/serve/app_init.py` `register_middleware()` | delete the TenantResolutionMiddleware mount; framework auto-mounts via `tenant_host:` blocks |

## Build sequence (slices)

Each slice is an independent PR + version bump, following the [[staged_ir_first_ship]] pattern.

| # | Slice | Estimated lines |
|---|---|---|
| 1 | IR + lexer + parser + grammar + validator. Stub middleware that raises `NotImplementedError` if mounted. | ~150 |
| 2 | Cache module + resolver module — pure-logic units with full unit coverage. | ~100 |
| 3 | Middleware + app_factory auto-mount + system-context Repository read path — wires resolution + 404 / 301 / 410. | ~120 |
| 4 | Cookie name switch + login-flow wiring. | ~80 |
| 5 | Cross-tenant guard + auth-dependency integration. | ~80 |
| 6 | Auto-bust hook into Repository.update + manual `dazzle.tenant.bust()`. | ~50 |
| 7 | Docs + AegisMark pin-bump filing — `docs/reference/tenant-hosts.md`, CHANGELOG Agent Guidance bullet. | ~50 docs |

**Total:** ~580 lines across 7 slices.

## Out of scope

- Slug history primitive on the `slug:` field itself (Phase 3 of #1288, separate issue)
- Tenant admin workspace primitive (the rename UI; potential follow-up `tenant_admin_workspace:` keyword)
- Per-tenant Cloudflare / Heroku API automation (this design assumes wildcard DNS only)
- Tenant-aware rate limiting (the existing `security_profile=standard` rate limiter is per-IP today; tenant-aware rate-limiting can layer on later)

## Open questions deferred to implementation

These are answer-during-implementation rather than design-time:

- Exact wording of the framework default 404 / 410 pages
- Logger categories for guard failures (probably `dazzle.tenant.guard`)
- Whether `dazzle inspect routes --runtime` should call out the tenant-mounted middleware in its output (likely yes, similar to the existing `auth` bucket)

## References

- Issue #1289 ([github.com/manwithacat/dazzle/issues/1289](https://github.com/manwithacat/dazzle/issues/1289))
- Paired issue #1288 (`slug:` field primitive — Phase 1 shipped v0.80.11)
- Prerequisite #1290 (project post-build hook — shipped v0.80.10; auto-mount in this design supersedes the need for projects to call `register_middleware()` for tenant resolution)
- ADR-0023 (no Jinja2 — drives the dotted-path callable template pattern)
- AegisMark proof-of-shape: `cyfutureuk/aegismark` main @ 3a3f706
