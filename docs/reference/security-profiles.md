# Security Profiles

Every Dazzle app declares a security profile in its `app` block. The profile
controls authentication defaults, HTTP security headers, and which admin
workspace regions are generated.

All profiles include authentication and an admin persona. Building without
auth is not a supported production configuration.

## Profile Comparison

| Feature | basic | standard | strict |
|---------|-------|----------|--------|
| Auth available | yes | yes | yes |
| `require_auth_by_default` | no | yes | yes |
| CORS | `*` (all origins) | same-origin | same-origin |
| HSTS header | no | yes | yes |
| CSP header | no | no | yes |
| Tenant isolation | no | no | yes (when `multi_tenant: true`) |

## Admin Workspace Regions by Profile

The linker auto-generates an admin workspace (`_platform_admin`) for every
app. The profile controls which regions are included.

| Region | basic | standard | strict |
|--------|-------|----------|--------|
| Users | yes | yes | yes |
| Health | yes | yes | yes |
| Deploys | yes | yes | yes |
| Metrics | yes | yes | yes |
| Feedback | if enabled | if enabled | if enabled |
| Sessions | — | yes | yes |
| Processes | — | yes | yes |
| Tenants | — | if multi-tenant | if multi-tenant |

Multi-tenant apps also get a `_tenant_admin` workspace with a subset of
these regions scoped to the current tenant.

## DSL Usage

```dsl
app my_app "My Application":
  security_profile: standard
  multi_tenant: false
```

Valid values: `basic`, `standard`, `strict`. Default is `basic`.

## When to Use Each Profile

**basic** — Prototypes, internal tools, hackathons. Auth is available but
surfaces are public by default. Use for rapid iteration where you don't
want to set up persona-gated surfaces yet.

**standard** — Production SaaS apps. Surfaces require auth by default.
Session management and process monitoring are available in the admin
workspace. This is the right choice for most apps.

**strict** — Regulated industries, multi-tenant platforms, apps handling
sensitive data. Adds CSP headers and tenant database isolation. Use when
you need defence-in-depth or compliance evidence.

## See Also

- [Access Control](access-control.md) — entity and surface permissions
- [Admin Workspace](../superpowers/specs/2026-03-26-admin-workspace-design.md) — design spec
