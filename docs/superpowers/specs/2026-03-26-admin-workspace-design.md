# Universal Admin Workspace Design

**Issue:** #686
**Date:** 2026-03-26
**Status:** Draft

## Summary

Every Dazzle app gets a framework-generated admin workspace. The linker synthesises platform entities (health, metrics, deploys, processes) and assembles them with existing entities (User, FeedbackReport, Session) into one or two admin workspaces gated by security profile and tenancy mode. The standalone ops/founder console is deprecated — its observability infrastructure becomes the backing store for the new workspace regions.

## Key Decisions

1. **Two workspaces in multi-tenant apps** — `_platform_admin` (super_admin, cross-tenant) and `_tenant_admin` (admin, tenant-scoped). Single-tenant apps get only `_platform_admin` with `["admin", "super_admin"]`.
2. **Always generated** — All three security profiles (basic, standard, strict) get an admin workspace. The profile controls which regions are included, not whether the workspace exists.
3. **No opt-out, no extension** — The admin workspace is closed framework infrastructure. Custom admin views go in user-authored workspaces.
4. **Synthetic entities for system data** — Health, metrics, and process data are modelled as entities with `domain: "platform"`, `patterns: ["system"]`, backed by existing Redis/in-memory stores via a `SystemEntityStore` adapter.
5. **Console deprecation** — The standalone `/_ops/` and `/_console/` apps are replaced. Dev control plane (`/dazzle/dev/*`) stays unchanged.
6. **Auth is universal** — Even `basic` profile apps have auth and an admin persona. Building without auth is no longer a goal for Dazzle.

## Phased Delivery

### Phase 1: Synthetic Platform Entities + SystemEntityStore

Define the system entities in the linker and wire the runtime to route reads to the appropriate backing stores.

#### Synthetic Entities

All use `domain: "platform"`, `patterns: ["system"]`. Access: `require_auth: true`, read+list only, gated to `admin`/`super_admin` personas.

| Entity | Key Fields | Backing Store | Profile Gate |
|--------|-----------|---------------|-------------|
| **SystemHealth** | component, status (healthy/degraded/unhealthy), message, checked_at | `health_aggregator.py` (in-memory) | all |
| **SystemMetric** | name, value (float), unit, tags (text), bucket_start, resolution | `metrics_store.py` (Redis streams) | standard+ |
| **DeployHistory** | version, previous_version, deployed_by, deployed_at, status, rollback_of | PostgreSQL (durable audit data) | all |
| **ProcessRun** | process_name, status, started_at, completed_at, current_step, error | `process_monitor.py` (Redis) | standard+ |
| **SessionInfo** | user_id, email, created_at, expires_at, ip_address, user_agent, is_active | `auth.store.SessionRecord` (PostgreSQL via auth store) | standard+ |

DeployHistory is the exception — it uses PostgreSQL because deploy records are durable audit data. It uses `patterns: ["system", "audit"]`.

#### SystemEntityStore

New file: `src/dazzle_back/runtime/system_entity_store.py`

Implements the same read/list interface as the PostgreSQL entity store. The workspace renderer calls `store.list(entity_name, filters, sort, limit)` and `store.get(entity_name, id)` without knowing the backing store.

Routing logic in entity resolution:

```python
VIRTUAL_ENTITIES = {"SystemHealth", "SystemMetric", "ProcessRun"}

def get_store(entity: EntitySpec) -> EntityStore:
    if entity.name in VIRTUAL_ENTITIES:
        return SystemEntityStore(entity)
    return PostgresEntityStore(entity)
```

Store adapters inside SystemEntityStore:

| Entity | Delegates To |
|--------|-------------|
| SystemHealth | `health_aggregator.get_component_statuses()` |
| SystemMetric | `metrics_store.query_timeseries()` |
| ProcessRun | `process_monitor.get_recent()` |

Write operations (create/update/delete) raise `NotImplementedError`.

#### Linker Integration

New file: `src/dazzle/core/admin_builder.py`

Single entry point: `build_admin_infrastructure()` called from `linker.py` after synthetic entity generation (line ~126) and before FK graph building (line ~128).

```python
# In build_appspec():
# 9c. Auto-generate admin platform entities + workspaces
entities, admin_surfaces, admin_workspaces = build_admin_infrastructure(
    entities=entities,
    surfaces=surfaces,
    security_config=security_config,
    app_config=root_module.app_config,
    feedback_widget=merged_fragment.feedback_widget,
    existing_workspaces=merged_fragment.workspaces,
)
surfaces = [*surfaces, *admin_surfaces]
workspaces = [*merged_fragment.workspaces, *admin_workspaces]
```

Collision avoidance: synthetic names use underscore prefix (`_platform_admin`, `_tenant_admin`). The builder checks for user-declared entities/workspaces with the same names and raises `LinkError` on collision.

### Phase 2: Admin Workspaces

Build the workspace specifications from the canonical region list, filtered by profile and tenancy.

#### Region Definitions

| Region | Source Entity/Surface | Display | Profile | Multi-tenant only? |
|--------|----------------------|---------|---------|---------------------|
| `users` | User (archetype-expanded) | list | all | no |
| `feedback` | feedback_admin (existing surface) | list | all | only if feedback_widget enabled |
| `sessions` | SessionInfo | list | standard+ | no |
| `deploys` | DeployHistory | list | all | no |
| `health` | SystemHealth | grid | all | no |
| `metrics` | SystemMetric | bar_chart | standard+ | no |
| `processes` | ProcessRun | list | standard+ | no |
| `tenants` | Tenant (archetype-expanded) | list | standard+ | yes |

#### Workspace Specifications

**`_platform_admin`** (always generated):
- Multi-tenant: `allow_personas: ["super_admin"]`, all regions, cross-tenant data
- Single-tenant: `allow_personas: ["admin", "super_admin"]`, all regions (minus tenants)

**`_tenant_admin`** (multi-tenant only):
- `allow_personas: ["admin"]`
- Subset: users, feedback, sessions, deploys, health
- Entity scope predicates handle tenant isolation automatically

#### Nav Groups

Three sections per workspace:
- **Management**: users, tenants, sessions
- **Observability**: health, metrics, processes
- **Operations**: deploys, feedback

### Phase 3: Console Deprecation

#### Routes Retired

| Current Route | Replacement |
|---------------|-------------|
| `/_ops/health` | SystemHealth entity in `_platform_admin` |
| `/_ops/metrics/*` | SystemMetric entity regions |
| `/_ops/processes/*` | ProcessRun entity regions |
| `/_console/dashboard` | `_platform_admin` workspace home |
| `/_console/changes` | DeployHistory entity regions |
| `/_console/deploy` | DeployHistory (read-only in v1) |
| `/_console/performance` | SystemMetric regions |

#### What Stays

- Dev control plane (`/dazzle/dev/*`) — persona switching, scenario management, data reset. Unchanged.

#### Deprecation Mechanics

1. Mark console routes with `X-Dazzle-Deprecated: use admin workspace` header
2. Remove `enable_console` from ServerConfig
3. Remove ConsoleSubsystem from subsystem startup order
4. Delete: `src/dazzle_back/control_plane/`, `runtime/ops_routes.py`, `runtime/console_routes.py`, `templates/console/`

## Testing Strategy

### Phase 1 — Unit Tests

`test_admin_builder.py`:
- Verify correct entities generated for each profile x tenancy combination (6 cases: basic/standard/strict x single/multi-tenant)
- Verify collision detection: user-declared `SystemHealth` raises `LinkError`
- Verify field schemas match backing store shapes
- Verify access rules: read+list only, admin-persona-gated

`test_system_entity_store.py`:
- Verify reads delegate to health aggregator, metrics store, process monitor
- Verify DeployHistory routes to PostgreSQL
- Verify write operations raise `NotImplementedError`

### Phase 2 — Unit Tests

Extend `test_admin_builder.py`:
- Verify `_platform_admin` gets all regions for active profile
- Verify `_tenant_admin` gets correct subset with appropriate `allow_personas`
- Verify single-tenant apps only generate `_platform_admin` with `["admin", "super_admin"]`
- Verify feedback region only included when `feedback_widget.enabled`
- Verify nav group structure (Management / Observability / Operations)

### Phase 3 — Integration Tests

- Verify old console routes return deprecation headers
- Verify admin workspace regions render the same data the console used to

### Existing Tests

- `test_linker.py` extended with admin infrastructure cases
- Existing feedback widget tests unchanged

## Follow-Up Issues

1. Log viewer region — complex filtering UI, needs own design
2. App map / entity graph visualization region
3. Deploy trigger actions (write operations from admin workspace)
4. Event explorer migration to admin workspace
5. Review remaining control plane code for deprecation/repurposing
6. Update examples to reflect auth-is-universal philosophy (basic profile gets admin persona)
7. Clarify basic/standard/strict taxonomy in documentation
