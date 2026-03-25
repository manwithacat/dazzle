# ADR-0005: RuntimeServices Container

**Status:** Accepted
**Date:** 2026-03-25

## Context

The Dazzle runtime accumulated service state in module-level mutable singletons — one per concern (DB pool, event bus, channel registry, grant store, and others). This pattern was expedient but created two persistent problems:

1. **Test pollution** — tests that instantiate a service mutate shared global state. Teardown is unreliable and order-dependent.
2. **Multi-tenancy unsafety** — a future multi-tenant deployment cannot safely share module-level objects across request contexts.

Additionally, the MCP server maintained its own parallel globals (`_server_state`, `_project_root`) with no disciplined boundary between runtime and MCP concerns.

The runtime services implementation plan (issue #673) identified 11 module-level mutable singletons across `src/dazzle_back/` and `src/dazzle/mcp/`.

## Decision

Consolidate all FastAPI runtime service objects into a single **`RuntimeServices` dataclass** attached to `app.state.services`. MCP server state moves into a dedicated **`ServerState` dataclass** in the MCP layer.

Rules going forward:

- No new module-level mutable singletons in `src/dazzle_back/` or `src/dazzle/mcp/`.
- All existing necessary module-level globals annotated with `# noqa: PLW0603` as a forcing function for future elimination.
- Route handlers and middleware receive services via `request.app.state.services` or FastAPI `Depends()` — never via module imports.
- Tests construct a fresh `RuntimeServices` instance per test; no teardown of globals required.

### Container Shape

```python
@dataclass
class RuntimeServices:
    db: DatabasePool
    events: EventBus
    channels: ChannelRegistry
    grants: GrantStore
    cache: CacheBackend
```

`ServerState` mirrors the same principle for MCP: holds project root, KG reference, and active project selection.

## Consequences

### Positive

- Tests construct isolated service instances — no global teardown needed.
- Multi-tenant deployment can create one `RuntimeServices` per tenant context.
- Dependency graph is explicit and readable at the call site.
- `# noqa: PLW0603` annotations make all remaining globals visible in a single `ruff` report.

### Negative

- All route handlers must be updated to read from `request.app.state.services` rather than importing module-level objects.
- `lifespan` context manager must initialise and tear down the container.

### Neutral

- `ServerState` is a parallel but separate change — MCP and runtime lifecycles differ.
- No change to the public DSL, IR, or CLI surface.

## Alternatives Considered

### 1. Scattered Module-Level Getters/Setters

Keep the existing pattern but add `get_db()` / `set_db()` accessor functions.

**Rejected:** Cosmetic fix only. Still global mutable state; still causes test pollution.

### 2. Dependency Injection Container (e.g. `lagom`, `injector`)

Use a third-party DI framework to manage lifetimes.

**Rejected:** Heavy dependency for a problem a plain dataclass solves. Adds learning overhead for future contributors.

### 3. Thread-Local / ContextVar Storage

Store services in `contextvars.ContextVar` so each async context sees its own copy.

**Rejected:** Adds implicit context propagation that is harder to trace than an explicit parameter. Still requires discipline to initialise correctly.

## Implementation

See the runtime services implementation plan in `dev_docs/` (issue #673) for the phased migration steps covering service extraction, lifespan wiring, route handler updates, and test fixture changes.
