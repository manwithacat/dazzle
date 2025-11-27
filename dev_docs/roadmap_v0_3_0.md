# DAZZLE v0.3.0 Roadmap - UI Semantic Layout Engine

**Status**: Planning
**Target Release**: Q2-Q3 2026
**Focus**: Semantic UI Layout, Next.js Stack, Workspace Rendering
**Dependencies**: v0.2 DSL (workspaces, personas, attention signals)

> **📍 Navigation**: This document details v0.3.0 feature planning for the UI Semantic Layout Engine.
> For the master roadmap and version timeline, see **`/ROADMAP.md`** (single source of truth).

---

## Overview

Version 0.3.0 introduces a **deterministic, semantics-driven UI layout engine** that transforms DAZZLE's workspace and persona definitions into concrete, responsive user interfaces.

**Key Innovation**: Treat UI layout as a **compiler stage** rather than a runtime rendering problem.

**Goals**:
- Implement layout engine that consumes workspace semantics
- Generate deterministic layout plans from DSL
- Create `nextjs_semantic` stack for modern React UIs
- Support multiple layout archetypes (Focus Metric, Scanner Table, Dual Pane, Monitor Wall)
- Enable persona-aware UI optimization
- Maintain zero stochastic behavior (no AI for layout decisions)

**Reference**: See `dev_docs/architecture/dazzle_ui_semantic_layout_spec_v1.md` for complete specification.

---

## Architecture Overview

### Compilation Pipeline

```
DAZZLE DSL v0.2
  ↓
AppSpec (with workspaces, personas, attention signals)
  ↓
UI-Semantics IR (layout-specific enrichment)
  ↓
Layout Plan (archetype, surfaces, signal allocation)
  ↓
Concrete UI (Next.js + React components)
```

### Key Concepts

1. **Workspace**: Primary unit of user focus (dashboard/screen)
2. **Persona**: Role-based user profile affecting layout priorities
3. **Attention Signal**: Semantic UI element requiring user awareness (KPI, table, alert, etc.)
4. **Layout Archetype**: Named compositional pattern (Focus Metric, Scanner Table, etc.)
5. **Surface**: Logical area within layout (primary, secondary, sidebar, toolbar)
6. **Layout Plan**: Deterministic output specifying where each signal appears

---

## Phase 1: Core Layout Engine (3-4 weeks)

### Week 1: IR and Data Model

**Goal**: Extend DAZZLE IR with layout-specific types

**Tasks**:
- [ ] Add `WorkspaceLayout` to IR (extends workspace with layout attributes)
- [ ] Add `PersonaLayout` to IR (extends persona with UI biases)
- [ ] Add `AttentionSignal` to IR (semantic UI element)
- [ ] Add `LayoutPlan` to IR (output of layout engine)
- [ ] Add archetype definitions (FOCUS_METRIC, SCANNER_TABLE, DUAL_PANE_FLOW, MONITOR_WALL)
- [ ] Document all new IR types in `docs/DAZZLE_IR_0_1.md`

**Implementation Details**:

```python
# src/dazzle/core/ir.py additions

class AttentionSignalKind(str, Enum):
    KPI = "kpi"
    ALERT_FEED = "alert_feed"
    TABLE = "table"
    ITEM_LIST = "item_list"
    DETAIL_VIEW = "detail_view"
    TASK_LIST = "task_list"
    # ... more kinds

class AttentionSignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: AttentionSignalKind
    label: str
    source: str  # Entity/surface reference
    attention_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency: Literal["low", "medium", "high"] = "medium"
    interaction_frequency: Literal["rare", "occasional", "frequent"] = "occasional"
    density_preference: Literal["compact", "comfortable"] = "comfortable"
    mode: Literal["read", "act", "configure"] = "read"
    constraints: dict[str, Any] = Field(default_factory=dict)

class WorkspaceLayout(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    persona_targets: list[str] = Field(default_factory=list)
    attention_budget: float = Field(default=1.0, ge=0.0, le=1.5)
    time_horizon: Literal["realtime", "daily", "archival"] = "daily"
    engine_hint: Optional[str] = None
    attention_signals: list[AttentionSignal] = Field(default_factory=list)

class PersonaLayout(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    goals: list[str] = Field(default_factory=list)
    proficiency_level: Literal["novice", "intermediate", "expert"] = "intermediate"
    session_style: Literal["glance", "deep_work"] = "deep_work"
    attention_biases: dict[str, float] = Field(default_factory=dict)
```

**Tests**:
```bash
tests/unit/test_layout_ir.py
  - test_attention_signal_creation
  - test_workspace_layout_creation
  - test_persona_layout_creation
  - test_attention_weight_validation
  - test_immutability
```

**Estimate**: 4-5 days

---

### Week 2: Layout Algorithm

**Goal**: Implement pure, deterministic layout planning functions

**Tasks**:
- [ ] Implement archetype selection logic (`select_archetype()`)
- [ ] Implement surface allocation algorithm (`assign_signals_to_surfaces()`)
- [ ] Implement persona-aware attention adjustment (`adjust_attention_for_persona()`)
- [ ] Implement over-budget handling
- [ ] Implement layout plan assembly (`build_layout_plan()`)
- [ ] Add determinism tests (same inputs → same outputs)

**Module Structure**:

```
src/dazzle/ui/
├── __init__.py
├── layout_engine/
│   ├── __init__.py
│   ├── types.py              # Re-export IR types
│   ├── archetypes.py         # Archetype definitions
│   ├── select_archetype.py   # Selection logic
│   ├── allocate.py           # Surface allocation
│   ├── adjust.py             # Persona adjustments
│   └── plan.py               # Main orchestrator
└── renderers/
    └── __init__.py
```

**Key Functions**:

```python
# src/dazzle/ui/layout_engine/select_archetype.py

def select_archetype(
    workspace: WorkspaceLayout,
    persona: Optional[PersonaLayout] = None
) -> str:
    """
    Select layout archetype based on attention signal profile.

    Rules:
    - Single high-weight KPI/alert → FOCUS_METRIC
    - Dominant table/list → SCANNER_TABLE
    - List + detail view → DUAL_PANE_FLOW
    - Multiple moderate signals → MONITOR_WALL

    Returns archetype name (str).
    """
    # Deterministic rules based on signal kinds and weights
    ...


# src/dazzle/ui/layout_engine/allocate.py

def assign_signals_to_surfaces(
    workspace: WorkspaceLayout,
    archetype_def: ArchetypeDefinition
) -> tuple[list[Surface], list[str]]:
    """
    Allocate attention signals to surfaces using capacity management.

    Returns:
    - list[Surface]: Surfaces with assigned signals
    - list[str]: Over-budget signal IDs
    """
    # Sort signals by weight (descending)
    # Allocate to surfaces respecting capacity
    # Track over-budget signals
    ...


# src/dazzle/ui/layout_engine/plan.py

def build_layout_plan(
    workspace: WorkspaceLayout,
    persona: Optional[PersonaLayout] = None,
    engine_variant: str = "classic"
) -> LayoutPlan:
    """
    Main orchestrator: build complete layout plan.

    Pure function - same inputs always produce same output.
    """
    # 1. Adjust attention weights for persona
    # 2. Select archetype
    # 3. Get archetype definition
    # 4. Allocate signals to surfaces
    # 5. Handle over-budget signals
    # 6. Return LayoutPlan
    ...
```

**Tests**:
```bash
tests/unit/test_layout_engine.py
  - test_archetype_selection_focus_metric
  - test_archetype_selection_scanner_table
  - test_archetype_selection_dual_pane
  - test_archetype_selection_monitor_wall
  - test_surface_allocation_within_capacity
  - test_surface_allocation_over_budget
  - test_persona_attention_adjustment
  - test_determinism  # Critical: same inputs → same outputs
```

**Estimate**: 5-6 days

---

### Week 3: DSL Integration

**Goal**: Map DSL v0.2 constructs to layout IR

**Tasks**:
- [ ] Extract workspace layout metadata from DSL
- [ ] Extract persona layout attributes from DSL
- [ ] Map workspace data views to attention signals
- [ ] Map UX attention blocks to attention signals
- [ ] Implement `build_ui_semantics_ir(app_spec)` function
- [ ] Add integration tests

**DSL Mappings**:

```dsl
# DSL workspace block
workspace dashboard "Team Dashboard":
  purpose: "Real-time team overview"

  urgent_tasks:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    action: task_edit

  team_metrics:
    aggregate:
      total: count(Task)
      completed: count(Task where status = done)
      completion_rate: completed * 100 / total

# Maps to:
WorkspaceLayout(
    id="dashboard",
    label="Team Dashboard",
    attention_signals=[
        AttentionSignal(
            id="urgent_tasks",
            kind=AttentionSignalKind.ITEM_LIST,
            label="Urgent Tasks",
            source="Task",
            attention_weight=0.7,  # Inferred from filter+limit
            urgency="high"
        ),
        AttentionSignal(
            id="team_metrics",
            kind=AttentionSignalKind.KPI,
            label="Team Metrics",
            source="Task",
            attention_weight=0.6
        )
    ]
)
```

**Attention Signal Inference**:

```dsl
ux:
  attention critical:
    when: due_date < today and status != done
    message: "Overdue task"
    action: task_edit

# Maps to:
AttentionSignal(
    id="overdue_alert",
    kind=AttentionSignalKind.ALERT_FEED,
    urgency="high",  # From "critical"
    attention_weight=0.8  # Auto-boost for critical
)
```

**Tests**:
```bash
tests/integration/test_dsl_to_layout_ir.py
  - test_workspace_to_layout
  - test_persona_extraction
  - test_attention_signal_mapping
  - test_aggregate_becomes_kpi
  - test_filter_becomes_list
```

**Estimate**: 4-5 days

---

## Phase 2: Next.js Stack (3-4 weeks)

### Week 4: Stack Generator Core

**Goal**: Generate Next.js project structure with layout engine

**Tasks**:
- [ ] Implement `nextjs_semantic` stack class
- [ ] Generate Next.js App Router project structure
- [ ] Generate TypeScript layout engine code
- [ ] Generate layout plans at build time (JSON files)
- [ ] Generate package.json with dependencies
- [ ] Add stack to `src/dazzle/stacks/__init__.py`

**Stack Class**:

```python
# src/dazzle/stacks/nextjs_semantic.py

from pathlib import Path
from dazzle.stacks.base import BaseBackend, StackCapabilities
from dazzle.core import ir

class NextJsSemanticStack(BaseBackend):
    """Generate Next.js app with semantic layout engine."""

    def get_capabilities(self) -> StackCapabilities:
        return StackCapabilities(
            name="nextjs_semantic",
            description="Next.js with semantic workspace layouts",
            output_formats=["code"],
            supports_incremental=False
        )

    def generate(self, spec: ir.AppSpec, output_dir: Path, artifacts=None):
        """Generate complete Next.js application."""
        # 1. Create project structure
        # 2. Generate TypeScript types from IR
        # 3. Generate layout engine code
        # 4. Generate layout plans for each workspace
        # 5. Generate React components
        # 6. Generate API client for backends
        # 7. Generate config files
        ...
```

**Generated Structure**:

```
build/nextjs_semantic/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── workspaces/
│   │   ├── [workspace]/
│   │   │   └── page.tsx
│   │   └── layout_plans/
│   │       ├── dashboard.json
│   │       └── tasks.json
│   └── components/
│       ├── surfaces/
│       ├── signals/
│       └── archetypes/
├── lib/
│   ├── layout-engine/
│   │   ├── types.ts
│   │   ├── archetypes.ts
│   │   ├── select-archetype.ts
│   │   └── allocate-signals.ts
│   └── data/
│       └── api-client.ts
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── next.config.js
```

**Tests**:
```bash
tests/integration/test_nextjs_semantic_stack.py
  - test_generate_project_structure
  - test_layout_plans_generated
  - test_typescript_types_valid
  - test_package_json_correct
```

**Estimate**: 5-6 days

---

### Week 5: React Components

**Goal**: Generate archetype templates and signal components

**Tasks**:
- [ ] Implement `FocusMetricArchetype` component
- [ ] Implement `ScannerTableArchetype` component
- [ ] Implement `DualPaneArchetype` component
- [ ] Implement `MonitorWallArchetype` component
- [ ] Implement surface components (Primary, Secondary, Sidebar, etc.)
- [ ] Implement attention signal components (KPI, Table, Alert, etc.)
- [ ] Add Tailwind CSS styling
- [ ] Add responsive breakpoints

**Archetype Component Example**:

```typescript
// app/components/archetypes/FocusMetricArchetype.tsx

import { LayoutPlan, Surface } from '@/lib/layout-engine/types'
import { PrimarySurface } from '../surfaces/PrimarySurface'
import { SecondarySurface } from '../surfaces/SecondarySurface'

interface Props {
  plan: LayoutPlan
}

export function FocusMetricArchetype({ plan }: Props) {
  const primary = plan.surfaces.find(s => s.role === 'primary')
  const secondary = plan.surfaces.find(s => s.role === 'secondary')

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto p-6">
        {/* Hero metric takes 2/3 of vertical space */}
        {primary && (
          <div className="mb-6">
            <PrimarySurface surface={primary} signals={...} />
          </div>
        )}

        {/* Supporting panels in grid */}
        {secondary && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <SecondarySurface surface={secondary} signals={...} />
          </div>
        )}
      </div>
    </div>
  )
}
```

**Signal Component Example**:

```typescript
// app/components/signals/KPISignal.tsx

import { AttentionSignal } from '@/lib/layout-engine/types'

interface Props {
  signal: AttentionSignal
  data: any  // From API
}

export function KPISignal({ signal, data }: Props) {
  const { label, urgency, density_preference } = signal

  return (
    <div className={`
      rounded-lg border p-6
      ${urgency === 'high' ? 'border-red-500 bg-red-50' : 'border-gray-200'}
      ${density_preference === 'compact' ? 'p-4' : 'p-6'}
    `}>
      <div className="text-sm text-gray-600">{label}</div>
      <div className="text-4xl font-bold mt-2">{data.value}</div>
      {data.change && (
        <div className={`text-sm mt-1 ${
          data.change > 0 ? 'text-green-600' : 'text-red-600'
        }`}>
          {data.change > 0 ? '↑' : '↓'} {Math.abs(data.change)}%
        </div>
      )}
    </div>
  )
}
```

**Tests**:
```bash
tests/integration/test_nextjs_components.py
  - test_archetype_components_render
  - test_signal_components_render
  - test_responsive_layout
  - test_tailwind_classes_correct
```

**Estimate**: 5-6 days

---

### Week 6: Polish & Testing

**Goal**: Production-ready stack with full test coverage

**Tasks**:
- [ ] Add responsive layouts for mobile/tablet
- [ ] Add loading states and error boundaries
- [ ] Add accessibility (ARIA labels, keyboard nav)
- [ ] Implement golden master tests
- [ ] Create example projects for each archetype
- [ ] Add stack-specific documentation
- [ ] Performance optimization

**Example Projects**:

```bash
examples/semantic_dashboard/    # MONITOR_WALL archetype
examples/semantic_tasks/        # DUAL_PANE_FLOW archetype
examples/semantic_invoices/     # SCANNER_TABLE archetype
examples/semantic_metrics/      # FOCUS_METRIC archetype
```

**Golden Master Tests**:

```python
# tests/integration/golden_masters/test_layout_plans.py

def test_dashboard_layout_plan_matches_golden():
    """Ensure layout plan for dashboard is deterministic."""
    # Build AppSpec from DSL
    app_spec = build_from_dsl("examples/semantic_dashboard/dsl/app.dsl")

    # Generate layout plan
    workspace = app_spec.workspaces[0]
    plan = build_layout_plan(workspace, persona=None, engine="classic")

    # Compare to golden master
    golden_path = Path("tests/golden_masters/dashboard_plan.json")
    assert plan.model_dump() == json.loads(golden_path.read_text())
```

**Tests**:
```bash
tests/integration/golden_masters/
  - test_focus_metric_plan
  - test_scanner_table_plan
  - test_dual_pane_plan
  - test_monitor_wall_plan
  - test_persona_variants
```

**Estimate**: 5-6 days

---

## Phase 3: Tooling & Documentation (1-2 weeks)

### Week 7: CLI & MCP Integration

**Goal**: Make layout engine accessible via CLI and MCP

**Tasks**:
- [ ] Add `dazzle layout-plan` command
- [ ] Add MCP tools for layout planning
- [ ] Add VS Code preview support (optional)
- [ ] Complete documentation
- [ ] Create tutorial/walkthrough

**CLI Command**:

```python
# src/dazzle/cli.py

@app.command()
def layout_plan(
    workspace: str = typer.Argument(..., help="Workspace ID"),
    persona: Optional[str] = typer.Option(None, "--persona"),
    engine: str = typer.Option("classic", "--engine"),
    output: Optional[Path] = typer.Option(None, "--output", "-o")
):
    """Generate layout plan for a workspace."""
    # Load AppSpec
    # Find workspace and persona
    # Generate layout plan
    # Output JSON
    ...
```

**Usage**:
```bash
# Generate layout plan
dazzle layout-plan dashboard

# With persona optimization
dazzle layout-plan dashboard --persona admin

# Save to file
dazzle layout-plan dashboard -o layout.json

# Dense engine variant
dazzle layout-plan monitor --engine dense
```

**MCP Tools**:

```python
# src/dazzle/mcp/server.py

Tool(
    name="generate_layout_plan",
    description="Generate UI layout plan for workspace",
    inputSchema={
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string"},
            "persona_id": {"type": "string"},
            "engine": {"type": "string", "enum": ["classic", "dense", "playful"]}
        },
        "required": ["workspace_id"]
    }
),

Tool(
    name="preview_archetype",
    description="Preview archetype selection for workspace",
    inputSchema={
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string"}
        },
        "required": ["workspace_id"]
    }
)
```

**Documentation**:
- `docs/UI_SEMANTIC_LAYOUT.md` - Overview and concepts
- `docs/ARCHETYPES_REFERENCE.md` - Archetype details with diagrams
- `docs/stacks/NEXTJS_SEMANTIC.md` - Stack usage guide
- Update `docs/DAZZLE_DSL_REFERENCE.md` - Workspace examples

**Estimate**: 5-7 days

---

## Testing Strategy

### Unit Tests

**Coverage Target**: >90%

```bash
tests/unit/test_layout_ir.py              # IR types
tests/unit/test_archetypes.py             # Archetype definitions
tests/unit/test_select_archetype.py       # Selection logic
tests/unit/test_allocate_signals.py       # Allocation algorithm
tests/unit/test_adjust_attention.py       # Persona adjustments
tests/unit/test_layout_plan.py            # Full plan generation
```

### Integration Tests

```bash
tests/integration/test_dsl_to_layout_ir.py       # DSL → IR mapping
tests/integration/test_nextjs_semantic_stack.py  # Stack generation
tests/integration/test_nextjs_components.py      # Component rendering
```

### Golden Master Tests

```bash
tests/integration/golden_masters/test_layout_plans.py
  - Focus Metric archetype plan
  - Scanner Table archetype plan
  - Dual Pane archetype plan
  - Monitor Wall archetype plan
  - Persona variant plans
```

### Determinism Tests

**Critical**: Verify same inputs produce identical outputs

```python
def test_layout_plan_determinism():
    """Layout plan must be deterministic."""
    workspace = create_test_workspace()
    persona = create_test_persona()

    # Generate plan 100 times
    plans = [
        build_layout_plan(workspace, persona, "classic")
        for _ in range(100)
    ]

    # All plans must be identical
    assert len(set(p.model_dump_json() for p in plans)) == 1
```

---

## Success Criteria

**v0.3.0 is ready when**:

1. ✅ Layout engine generates deterministic layout plans
2. ✅ `nextjs_semantic` stack generates working Next.js apps
3. ✅ All 4 archetypes implemented and tested
4. ✅ Persona variants affect layout as expected
5. ✅ Over-budget signals handled gracefully (tabs/drawers)
6. ✅ Documentation complete with examples and diagrams
7. ✅ Golden master tests pass
8. ✅ Example projects demonstrate all archetypes
9. ✅ MCP tools available for layout planning
10. ✅ Zero random/stochastic behavior verified
11. ✅ Responsive layouts work on mobile/tablet
12. ✅ Accessibility standards met (ARIA, keyboard nav)

---

## Implementation Timeline

### Timeline Summary

- **Phase 1 (Core)**: 3-4 weeks
- **Phase 2 (Stack)**: 3-4 weeks
- **Phase 3 (Tooling)**: 1-2 weeks

**Total**: 7-10 weeks (2-2.5 months)

### Dependency Chain

```
Phase 1.1 (IR) → Phase 1.2 (Algorithm) → Phase 1.3 (DSL)
                                              ↓
Phase 2.1 (Generator) → Phase 2.2 (Components) → Phase 2.3 (Polish)
                                                       ↓
                                            Phase 3 (Tooling & Docs)
```

### Parallelization Opportunities

- **Documentation** can start in Phase 2 (concurrent with component work)
- **Example projects** can be created as components are completed
- **MCP tools** can be developed alongside CLI commands

---

## Risk Mitigation

### Risk 1: Archetype Selection Too Simplistic

**Probability**: Medium
**Impact**: Medium

**Mitigation**:
- Start with simple, clear rules
- Gather feedback from example projects
- Add more sophisticated rules in v0.3.1 if needed
- Allow explicit archetype override in DSL

### Risk 2: Capacity Algorithm Edge Cases

**Probability**: Low
**Impact**: Medium

**Mitigation**:
- Extensive unit tests with boundary conditions
- Golden master tests catch regressions
- Clear documentation of capacity logic
- Configurable capacity values per archetype

### Risk 3: Next.js Stack Complexity

**Probability**: Medium
**Impact**: High

**Mitigation**:
- Start with simplest possible components
- Use well-established UI libraries (Tailwind, Shadcn)
- Generate minimal code, rely on libraries
- Provide clear customization points for users

### Risk 4: DSL Integration Breaking Changes

**Probability**: Low
**Impact**: High

**Mitigation**:
- Layout features are additive (don't break existing DSL)
- Workspace/persona blocks already in v0.2
- Attention signals already defined
- Only *enrich* existing IR, don't modify

---

## Future Enhancements (v0.4.0+)

### Additional Archetypes

- **Command Center**: Operations dashboard with real-time alerts
- **Kanban Board**: Task/workflow management
- **Analytics Dashboard**: Chart-heavy layouts
- **Settings Panel**: Configuration-focused layouts

### Engine Variants

- **Dense**: Higher information density for power users
- **Playful**: Card-heavy, colorful layouts
- **Minimal**: Clean, spacious designs
- **Accessibility**: High-contrast, keyboard-first

### Advanced Features

- **Layout Animations**: Smooth transitions between states
- **Adaptive Layouts**: Time-of-day or context-aware changes
- **Layout Composition**: Combine multiple workspaces
- **Custom Archetypes**: User-defined archetype templates
- **Visual Editor**: Drag-and-drop layout customization

---

## Dependencies

### External Dependencies

**Next.js Stack**:
- Next.js 14+ (App Router)
- React 18+
- TypeScript 5+
- Tailwind CSS 3+
- Shadcn/UI or Mantine (component library)

**Development**:
- Vitest or Jest (TypeScript testing)
- Playwright (component testing)
- Storybook (component preview - optional)

### DAZZLE Dependencies

- **DSL v0.2**: Workspace and persona definitions
- **IR v0.1**: Core type system
- **Parser**: Workspace/persona parsing
- **Linker**: AppSpec construction

---

## Migration Path

**From v0.2 to v0.3**:

1. No breaking changes to existing DSL
2. Workspace and persona blocks enhanced with layout hints
3. Existing stacks (django, express) unaffected
4. `nextjs_semantic` stack is new, opt-in
5. Layout engine is isolated module

**Example Migration**:

```dsl
# v0.2 - still works
workspace dashboard "Dashboard":
  purpose: "Team overview"
  # ... data views

# v0.3 - enhanced with layout hints (optional)
workspace dashboard "Dashboard":
  purpose: "Team overview"
  layout_hint: "monitor_wall"  # NEW: Explicit archetype
  attention_budget: 1.2         # NEW: Custom capacity
  # ... data views
```

---

## Documentation Deliverables

### User Documentation

1. **`docs/UI_SEMANTIC_LAYOUT.md`**
   - High-level overview
   - How workspaces → layouts
   - Archetype descriptions
   - Persona influence

2. **`docs/ARCHETYPES_REFERENCE.md`**
   - Each archetype in detail
   - Surface definitions
   - Selection criteria
   - Visual diagrams

3. **`docs/stacks/NEXTJS_SEMANTIC.md`**
   - Stack usage guide
   - Generated structure
   - Customization guide
   - Deployment instructions

4. **Update `docs/DAZZLE_DSL_REFERENCE.md`**
   - Workspace layout examples
   - Persona UI impact
   - Layout hint syntax

### Developer Documentation

1. **`dev_docs/architecture/layout_engine_design.md`**
   - Architecture decisions
   - Algorithm explanations
   - Extension points

2. **`dev_docs/ui/adding_archetypes.md`**
   - How to add new archetypes
   - Surface definition guide
   - Component patterns

3. **API Documentation**
   - Type signatures
   - Function documentation
   - Examples

---

**Status**: Ready for Approval
**Next Steps**:
1. Review specification
2. Approve roadmap
3. Begin Phase 1 implementation
4. Create feature branch for UI layout engine
