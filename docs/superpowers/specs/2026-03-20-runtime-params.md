# Runtime Parameters — Tenant-Scoped Configuration for DSL Constructs

**Date**: 2026-03-20
**Status**: Proposed
**Issue**: #572

## Problem

DSL constructs accept only static values. But operational parameters — thresholds, timeouts, display preferences, retry counts — need to vary by tenant, by school policy, or by deployment. Rebuilding the app per tenant is not viable. The DSL should declare *what can vary* and *what the safe default is*, while runtime configuration provides per-scope values.

## Design Principles

1. **DSL declares parameters, runtime resolves them.** The IR contains `ParamRef` nodes, not baked-in values. Resolution is per-request, scoped to the current tenant.
2. **Defaults are mandatory.** Every param has a DSL-declared default. The app always works without any runtime overrides.
3. **Typed and constrained.** Params have declared types and validation constraints. Invalid values are rejected at write time, not discovered at render time.
4. **Scope cascade.** Resolution: user → tenant → system → DSL default. Provenance is always traceable.
5. **No runtime-created params.** The DSL is the source of truth for what CAN vary. The runtime only sets values for declared params.
6. **Security invariants are not params.** Scope rules, permit rules, and RBAC configuration are never parameterisable. Only operational/display parameters qualify.

## Section 1: DSL Syntax

### Parameter Declaration

```dsl
param heatmap.rag.thresholds:
  type: list[float]
  default: [40, 60]
  scope: tenant
  constraints:
    min_length: 2
    max_length: 5
    ordered: ascending
    range: [0, 100]
  description: "RAG boundary percentages for heatmap cells"
  category: "Assessment Display"
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `type` | yes | `bool`, `int`, `float`, `str`, `list[float]`, `list[str]`, `json` |
| `default` | yes | Literal default value, validated against type + constraints |
| `scope` | yes | `system`, `tenant`, or `user` — highest scope level at which this param can be overridden |
| `constraints` | no | Validation rules (see Section 4) |
| `description` | no | Human-readable description for admin UI / MCP |
| `category` | no | Dot-prefix grouping for admin UI (e.g., "Assessment Display") |
| `depends_on` | no | List of other param keys — UI warns when editing related params |
| `sensitive` | no | `true` to mask in logs/UI (for API keys, secrets) |

### Parameter Reference in Constructs

```dsl
region class_performance:
  source: MarkingResult
  display: heatmap
  thresholds: param("heatmap.rag.thresholds")

schedule nightly_sync:
  cron: param("sync.cron_expression")

sla response_time:
  deadline: param("support.response_hours")
```

`param("key")` can appear anywhere a literal value is accepted. The parser emits a `ParamRef` IR node instead of a literal.

### Dot Notation Hierarchy

Parameters use dot-separated hierarchical keys, grouped by category:

```
heatmap.rag.thresholds
heatmap.rag.color_scheme
grading.display.format
grading.display.decimal_places
attendance.alert.absent_threshold
attendance.alert.late_threshold
sync.cron_expression
sync.retry_count
sync.timeout_seconds
support.response_hours
support.escalation_hours
```

The first segment is the category. The admin UI groups by category automatically.

## Section 2: IR Representation

### ParamRef Node

```python
class ParamRef(BaseModel):
    """Reference to a runtime-resolved parameter."""
    model_config = ConfigDict(frozen=True)

    key: str                  # "heatmap.rag.thresholds"
    param_type: str           # "list[float]"
    default: Any              # [40, 60]
```

### ParamSpec (top-level IR)

```python
class ParamConstraints(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    ordered: str | None = None        # "ascending" | "descending"
    range: list[float] | None = None  # [min, max] for list elements
    enum_values: list[str] | None = None
    pattern: str | None = None        # regex for string params

class ParamSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    param_type: str
    default: Any
    scope: Literal["system", "tenant", "user"]
    constraints: ParamConstraints | None = None
    description: str | None = None
    category: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    sensitive: bool = False
```

`AppSpec.params: list[ParamSpec]` added to the root IR.

### Where ParamRef Replaces Literals

Any IR field that currently accepts a scalar or list can accept `ParamRef | <original_type>`. The fields most likely to be parameterised:

| Construct | Field | Type |
|-----------|-------|------|
| WorkspaceRegion | heatmap_thresholds | `list[float] \| ParamRef` |
| WorkspaceRegion | limit | `int \| ParamRef` |
| ScheduleSpec | cron | `str \| ParamRef` |
| SLASpec | deadline_hours | `int \| ParamRef` |
| ProcessStepSpec | timeout | `int \| ParamRef` |
| IntegrationSpec | rate_limit | `int \| ParamRef` |

The type union is added incrementally — only fields that have a real use case get ParamRef support.

## Section 3: Storage

### Table

```sql
CREATE TABLE _dazzle_params (
    key         TEXT NOT NULL,
    scope       TEXT NOT NULL,          -- 'system' | 'tenant' | 'user'
    scope_id    TEXT NOT NULL DEFAULT '',  -- tenant slug or user id; '' for system
    value_json  JSONB NOT NULL,
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (key, scope, scope_id)
);
```

Created by `auto_migrate` (framework table, public schema only — not per-tenant).

### Resolution Query

```sql
SELECT value_json, scope, scope_id
FROM _dazzle_params
WHERE key = $1
  AND (
    (scope = 'user' AND scope_id = $2)
    OR (scope = 'tenant' AND scope_id = $3)
    OR (scope = 'system' AND scope_id = '')
  )
ORDER BY
  CASE scope
    WHEN 'user' THEN 1
    WHEN 'tenant' THEN 2
    WHEN 'system' THEN 3
  END
LIMIT 1;
```

If no rows returned, use DSL default.

### Caching

Per-tenant in-memory dict with 60-second TTL. Invalidated on write via `ParamStore.set()`. Params change rarely (school admin tweaks once per term). The cache is per-process — no cross-process invalidation needed for single-dyno deploys. Multi-worker deploys use TTL expiry.

## Section 4: Validation & Constraints

### At DSL Parse Time

- Param key is valid dot-notation (`[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+`)
- Type is a supported param type
- Default value passes type check and constraint check
- No duplicate param keys

### At Runtime Write Time (admin UI / MCP)

```python
def validate_param_value(spec: ParamSpec, value: Any) -> list[str]:
    """Validate a proposed value against the param's declared type and constraints."""
    errors = []
    # Type check
    if spec.param_type == "list[float]" and not isinstance(value, list):
        errors.append(f"Expected list, got {type(value).__name__}")
    # Constraint checks
    if spec.constraints:
        c = spec.constraints
        if c.min_length and isinstance(value, list) and len(value) < c.min_length:
            errors.append(f"Minimum length {c.min_length}, got {len(value)}")
        if c.ordered == "ascending" and isinstance(value, list):
            if value != sorted(value):
                errors.append("Values must be in ascending order")
        if c.range and isinstance(value, list):
            lo, hi = c.range
            for v in value:
                if not (lo <= v <= hi):
                    errors.append(f"Value {v} outside range [{lo}, {hi}]")
    return errors
```

### Startup Validation

On server startup, after `auto_migrate`:
1. Load all stored overrides from `_dazzle_params`
2. For each, check that the key matches a declared `ParamSpec`
3. Validate the stored value against current type + constraints
4. Log warnings for mismatches (don't crash — stale overrides shouldn't prevent boot)
5. Remove or flag params whose keys no longer exist in DSL

## Section 5: Runtime Resolver

```python
class ParamResolver:
    """Resolves param references at request time."""

    def __init__(self, store: ParamStore, specs: dict[str, ParamSpec]):
        self._store = store
        self._specs = specs
        self._cache: dict[str, tuple[Any, float]] = {}  # key → (value, expiry)

    def resolve(
        self,
        key: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[Any, str]:
        """Resolve a param value. Returns (value, source).

        Source is one of: "user/{id}", "tenant/{id}", "system", "default".
        """
        spec = self._specs.get(key)
        if spec is None:
            raise KeyError(f"Unknown param: {key}")

        # Check cache
        cache_key = f"{key}:{tenant_id or ''}:{user_id or ''}"
        cached = self._cache.get(cache_key)
        if cached and cached[1] > time.time():
            return cached[0]

        # DB lookup with cascade
        result = self._store.resolve(key, tenant_id=tenant_id, user_id=user_id)
        if result is not None:
            value, scope, scope_id = result
            source = f"{scope}/{scope_id}" if scope_id else scope
            self._cache[cache_key] = ((value, source), time.time() + 60)
            return value, source

        # DSL default
        return spec.default, "default"
```

### Integration with Region Rendering

In `_workspace_region_handler`, when processing heatmap thresholds:

```python
# Before: static from IR
thresholds = list(getattr(ctx.ctx_region, "heatmap_thresholds", None) or [])

# After: resolve if ParamRef
raw = getattr(ctx.ctx_region, "heatmap_thresholds", None)
if isinstance(raw, ParamRef):
    thresholds, _source = param_resolver.resolve(
        raw.key, tenant_id=current_tenant_id
    )
else:
    thresholds = list(raw or [])
```

This pattern is the same everywhere a ParamRef might appear. A helper simplifies it:

```python
def resolve_value(raw: Any, resolver: ParamResolver, tenant_id: str | None) -> Any:
    """Resolve a value that might be a ParamRef or a literal."""
    if isinstance(raw, ParamRef):
        value, _source = resolver.resolve(raw.key, tenant_id=tenant_id)
        return value
    return raw
```

## Section 6: MCP & CLI

### MCP Operations (read-only)

Added to a new `param` tool:

- `param list` — list all declared params with current values for active tenant
- `param get {key}` — get param value with provenance (value, source, default, constraints)
- `param schema` — export all param declarations as JSON (for agent consumption)

### CLI Commands (writes)

```bash
dazzle param list                                    # all params with defaults
dazzle param get heatmap.rag.thresholds              # value + provenance
dazzle param set heatmap.rag.thresholds '[30, 70]'   # system scope
dazzle param set heatmap.rag.thresholds '[4, 7]' --tenant cyfuture
dazzle param reset heatmap.rag.thresholds --tenant cyfuture  # remove override
dazzle param validate                                # check all stored values
```

## Section 7: Auto-Generated Admin UI

A settings page at `/app/settings/params` (admin-only workspace):

- Grouped by `category` (dot-prefix first segment)
- Type-appropriate inputs: toggle for bool, number input for int/float, JSON editor for complex types
- Shows current effective value + provenance badge ("Default", "System Override", "Tenant Override")
- Validation on save — constraints enforced client-side and server-side
- `depends_on` shows a warning banner: "Changing this may affect: {related params}"
- `sensitive` params show masked values with reveal toggle

This page is generated from `AppSpec.params` at startup — no template to maintain.

## Section 8: Edge Cases

### Param declared, then removed from DSL
Stored overrides become orphaned. Startup validation logs a warning. `dazzle param validate` lists orphans. `dazzle param cleanup` removes them.

### Param type changes between deploys
Old stored values may not match new type. Startup validation catches this and logs a warning. The old value is ignored (DSL default used) until an admin sets a new valid value.

### Tenant deleted
Tenant overrides remain in `_dazzle_params` as dead rows. `dazzle param cleanup` removes overrides for non-existent tenants.

### Circular depends_on
Prevented at parse time — `depends_on` references are validated as a DAG (no cycles).

### What CANNOT be a param
- Scope rules (`scope:`, `permit:`) — security invariants
- Entity field types — schema changes
- FK relationships — structural
- State machine transitions — workflow logic
- Anything that would change the IR structure (adding/removing entities, surfaces, etc.)

Rule of thumb: if changing the value would require re-parsing DSL or re-running migrations, it's not a param.

## Section 9: Files Affected

### New files
- `src/dazzle/core/ir/params.py` — ParamSpec, ParamRef, ParamConstraints
- `src/dazzle/runtime/param_store.py` — DB storage + resolver
- `src/dazzle/cli/param.py` — CLI commands
- `src/dazzle/mcp/server/handlers/param.py` — MCP operations
- `tests/unit/test_params.py`

### Modified files
- `src/dazzle/core/ir/appspec.py` — add `params: list[ParamSpec]`
- `src/dazzle/core/lexer.py` — add `PARAM` token
- `src/dazzle/core/dsl_parser_impl/` — param declaration + param() reference parsing
- `src/dazzle/core/ir/workspaces.py` — `heatmap_thresholds: list[float] | ParamRef`
- `src/dazzle_back/runtime/workspace_rendering.py` — resolve ParamRef before use
- `src/dazzle_back/runtime/server.py` — create ParamResolver at startup
- `src/dazzle_back/runtime/migrations.py` — create `_dazzle_params` table
