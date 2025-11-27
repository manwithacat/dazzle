# DSL Integration Session - 2025-11-27

## Summary

Completed DSL integration (Phase 1, Week 3 from v0.3.0 roadmap), implementing automatic conversion from WorkspaceSpec (parsed DSL) to WorkspaceLayout (layout engine IR).

## Accomplishments

### 1. DSL to Layout IR Converter

Created `src/dazzle/ui/layout_engine/converter.py` (~220 lines) with three main functions:

- **`convert_workspace_to_layout(workspace: WorkspaceSpec) -> WorkspaceLayout`**
  - Converts single workspace from DSL parser to layout engine IR
  - Extracts attention signals from workspace regions
  - Infers signal kinds and calculates attention weights

- **`convert_workspaces_to_layouts(app_spec: AppSpec) -> list[WorkspaceLayout]`**
  - Batch converts all workspaces in an AppSpec

- **`enrich_app_spec_with_layouts(app_spec: AppSpec) -> AppSpec`**
  - Creates new AppSpec with `ux` field populated
  - Enables seamless DSL → Layout Engine workflow

### 2. Attention Signal Inference

Implemented intelligent signal kind inference from workspace region characteristics:

```python
def _infer_signal_kind_from_region(region) -> AttentionSignalKind:
    # aggregates → KPI
    if region.aggregates:
        return AttentionSignalKind.KPI

    # filter + limit → ITEM_LIST (curated subset)
    if region.filter and region.limit:
        return AttentionSignalKind.ITEM_LIST

    # limit alone → ITEM_LIST (top N)
    if region.limit:
        return AttentionSignalKind.ITEM_LIST

    # timeline/map display → CHART
    if "timeline" in display or "map" in display:
        return AttentionSignalKind.CHART

    # default → TABLE (browse all data)
    return AttentionSignalKind.TABLE
```

### 3. Attention Weight Calculation

Implemented weight calculation based on region properties:

```python
def _calculate_attention_weight(region) -> float:
    weight = 0.5  # Base weight

    # Boost for filtered views (+0.2)
    if region.filter:
        weight += 0.2

    # Boost for limited views (+0.1)
    if region.limit:
        weight += 0.1

    # Boost for aggregates/KPIs (+0.2)
    if region.aggregates:
        weight += 0.2

    return min(1.0, max(0.0, weight))  # Clamp to [0.0, 1.0]
```

### 4. Backend Integration

Modified `nextjs_semantic/backend.py` to auto-convert WorkspaceSpec:

```python
def _generate_layout_plans(self) -> None:
    # Auto-convert WorkspaceSpec to WorkspaceLayout if needed
    if not self.spec.ux or not self.spec.ux.workspaces:
        if self.spec.workspaces:
            self.spec = enrich_app_spec_with_layouts(self.spec)
```

### 5. Example DSL with Workspaces

Added workspace definitions to `examples/simple_task/dsl/app.dsl`:

```dsl
workspace dashboard "Task Dashboard":
  purpose: "Overview of all tasks with key metrics"

  task_count:
    source: Task
    aggregate:
      total: count(Task)

  urgent_tasks:
    source: Task
    limit: 5

  all_tasks:
    source: Task

workspace my_work "My Work":
  purpose: "Personal task view for assigned work"

  in_progress:
    source: Task
    limit: 10

  upcoming:
    source: Task
    limit: 5
```

### 6. Bug Fixes in Next.js Semantic Stack

Fixed two critical bugs in `nextjs_semantic/generators/types.py`:

1. **Fixed field.required → field.is_required**
   - FieldSpec has `.is_required` property, not `.required` attribute

2. **Fixed FieldType mapping**
   - Changed from using `field.type` (unhashable FieldType object)
   - To using `field.type.kind` (FieldTypeKind enum)
   - Updated type mapping to use enum values as dictionary keys

### 7. Comprehensive Tests

Created `tests/unit/test_layout_converter.py` with 8 tests (all passing):

```python
class TestWorkspaceConversion:
    def test_convert_simple_workspace()
    def test_convert_workspace_with_aggregate()
    def test_convert_multiple_workspaces()
    def test_enrich_app_spec()

class TestSignalInference:
    def test_limited_becomes_item_list()
    def test_no_limit_becomes_table()
    def test_aggregate_boosts_weight()
    def test_weight_clamping()
```

## End-to-End Verification

Successfully tested complete pipeline:

1. **DSL**: `examples/simple_task/dsl/app.dsl` with workspaces
2. **Parse**: DSL parser creates WorkspaceSpec with regions
3. **Convert**: Converter transforms to WorkspaceLayout with attention signals
4. **Plan**: Layout engine selects archetype (MONITOR_WALL) and allocates surfaces
5. **Generate**: Next.js pages created at `src/app/{dashboard,my_work}/page.tsx`

Generated dashboard page includes:
- Correct layout archetype (MONITOR_WALL)
- Proper signal kinds (KPI, ITEM_LIST, TABLE)
- Calculated attention weights (0.7, 0.6, 0.5)
- Surface allocation with priorities
- Attention budget warnings

## Files Created/Modified

### Created
- `src/dazzle/ui/layout_engine/converter.py` (~220 lines)
- `tests/unit/test_layout_converter.py` (~224 lines)

### Modified
- `src/dazzle/ui/layout_engine/__init__.py` (exported converter functions)
- `src/dazzle/stacks/nextjs_semantic/backend.py` (auto-conversion)
- `src/dazzle/stacks/nextjs_semantic/generators/types.py` (bug fixes)
- `src/dazzle/cli.py` (added traceback to build errors)
- `examples/simple_task/dsl/app.dsl` (added workspaces)

## Commits

1. `cbf6edb` - feat(layout): implement DSL to layout IR converter
2. `7b4581a` - fix(nextjs-semantic): correct field type mapping in TypeScript generator
3. `c4d39a1` - feat(examples): add workspace definitions to simple_task

## Key Learnings

1. **WorkspaceRegion has no `title` field** - regions use `name` for identification
2. **DSL syntax uses `aggregate:` (singular)** - not `aggregates:` for the keyword
3. **Region names don't need `region` prefix** - just `region_name:` in DSL
4. **FieldSpec uses `is_required` property** - not `required` attribute
5. **FieldType is unhashable** - must use `field.type.kind` (enum) as dict key
6. **Display mode ≠ Signal kind** - "list" display can still be TABLE signal

## Testing Strategy

- Unit tests for converter functions
- Signal inference tests for different region patterns
- Attention weight calculation tests
- End-to-end build test with actual example

## Roadmap Progress

**Phase 1 (Weeks 1-4): Foundation** - IN PROGRESS

- ✅ Week 1-2: Next.js stack (COMPLETE)
- ✅ Week 3: DSL integration (COMPLETE)
- ⏭️ Week 4: Tooling & CLI commands

**Next Steps**:
- Add `dazzle layout-plan` CLI command
- Update documentation with workspace examples
- Create additional example projects with workspaces
- Add persona variant support to converter

## Notes for Future Work

### Potential Enhancements to Converter

1. **Persona Support**: Extract persona targets from UX spec variants
2. **Time Horizon Inference**: Infer from region filters/sorts (e.g., "due_date < tomorrow" → "daily")
3. **Engine Hints**: Parse UX spec for explicit layout hints
4. **Rich Labels**: Use region context to generate better human-readable labels
5. **Enum Union Types**: Generate proper TypeScript union types for enum fields
6. **Entity References**: Use actual entity type references instead of "string" for ref fields

### Documentation Updates Needed

1. Add workspace DSL syntax to reference guide
2. Document attention signal inference rules
3. Add examples of different workspace patterns
4. Explain attention weight calculation
5. Show end-to-end DSL → Layout workflow

---

**Status**: DSL Integration COMPLETE ✅
**Duration**: ~2 hours
**Tests**: 8/8 passing
**Build**: Successful with nextjs_semantic stack
