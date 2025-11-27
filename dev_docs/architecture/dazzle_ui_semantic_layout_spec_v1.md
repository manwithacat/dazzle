# DAZZLE UI Semantics and Layout Engine Specification (v1)

**Status**: Specification
**Target Version**: v0.3.0
**Dependencies**: DAZZLE DSL v0.2 (workspaces, personas, attention signals)
**Updated**: 2025-11-27

## 1. Purpose and Scope

1. Implement a **deterministic, semantics-driven UI layout engine** for DAZZLE.
2. Treat the UI layout system as a compiler stage:

   - **DAZZLE DSL v0.2** → **AppSpec** → **UI-Semantics IR** → **Layout Plan** → **Concrete UI** (React/Next.js/CSS)

3. Do **not** rely on screenshots, vision models, or stochastic layout generation at runtime.
4. Consume the semantic description of **workspaces, personas, and attention signals** already present in DAZZLE DSL v0.2 and emit a structured **layout plan** that can be rendered by one or more UI renderers (e.g. Next.js + Tailwind/Mantine).

### Integration with DAZZLE

This specification extends DAZZLE's existing capabilities:

- **Builds on v0.2 DSL**: Uses `workspace`, `persona`, and `attention` constructs already defined
- **New Stack Target**: Adds `nextjs_semantic` stack that generates semantically-aware layouts
- **Complements Existing Stacks**: Works alongside `django_micro_modular`, `express_micro`, etc.
- **Deterministic Code Generation**: Maintains DAZZLE's philosophy of reproducible builds

---

## 2. Core Concepts and Data Model

### 2.1 Workspace

1. Represent a **workspace** as the primary unit of user focus (roughly equivalent to a “dashboard” or “main screen”).
2. Define the following fields for a workspace:

   - `id`: string, unique identifier.
   - `label`: human-readable name.
   - `persona_targets`: list of persona IDs or tags that this workspace is designed for.
   - `attention_budget`: numeric, default range [0.0, 1.5]; represents how much cumulative attention can be presented before the workspace is considered “overloaded”.
   - `time_horizon`: enum: `"realtime" | "daily" | "archival"`; describes how often the content is expected to change.
   - `engine_hint` (optional): string tag to select a layout engine variant (e.g. `"classic"`, `"dense"`, `"playful"`).

3. Ensure that workspaces are serializable as JSON/YAML and can be referenced from the AppSpec.

### 2.2 Persona

1. Represent **personas** as modifiers for layout and attention.
2. Define the following fields for a persona:

   - `id`: string, unique identifier.
   - `label`: human-readable name.
   - `goals`: list of tags (e.g. `"monitor-kpis"`, `"triage-errors"`, `"bulk-edit"`, `"configure-settings"`).
   - `proficiency_level`: enum: `"novice" | "intermediate | "expert"`.
   - `session_style`: enum: `"glance" | "deep-work"`.
   - `attention_biases`: optional mapping from `attention_signal.kind` to numeric multiplier (e.g. `{ "alert": 1.2, "kpi": 1.1, "table": 0.9 }`).

3. Allow the layout engine to select a **primary persona** for a given workspace or allow the caller to specify one explicitly.

### 2.3 Attention Signal

1. Represent **attention signals** as semantic UI elements that require user awareness or interaction.
2. Define at least the following fields:

   - `id`: string, unique identifier.
   - `kind`: enum-like string, e.g. `"kpi"`, `"alert-feed"`, `"table"`, `"item-list"`, `"detail-view"`, `"task-list"`, `"control-panel"`, `"chart"`, `"stat-card"`, `"form"`, `"timeline"`, `"filters"`, `"navigation"`.
   - `label`: human-readable name.
   - `source`: reference to a backend resource, query, or domain entity (e.g. `"invoices.overdue_count"`, `"orders.list"`).
   - `attention_weight`: numeric in [0.0, 1.0]; how important this signal is relative to other signals in the same workspace.
   - `urgency`: enum: `"low" | "medium" | "high"`.
   - `interaction_frequency`: enum: `"rare" | "occasional" | "frequent"`.
   - `density_preference`: enum: `"compact" | "comfortable"`.
   - `mode`: enum: `"read" | "act" | "configure"`.
   - `constraints`: optional dictionary of constraints, e.g. `{ "min_width": "md", "requires_detail_pane": true }`.

3. Place attention signals inside a workspace via a `workspace.attention_signals` collection.
4. Ensure attention signals are serializable and referenced by `id` in later layout stages.

### 2.4 Surfaces and Zones

1. Represent **surfaces/zones** as logical areas within a workspace layout.
2. Define the following fields for a surface:

   - `id`: string, unique identifier (e.g. `"primary"`, `"secondary"`, `"sidebar"`, `"footer"`, `"toolbar"`, `"overlay"`).
   - `role`: enum: `"primary" | "secondary" | "peripheral" | "modal" | "toolbar" | "navigation"`.
   - `capacity`: numeric in [0.0, 1.0]; maximum cumulative attention weight recommended in this surface.
   - `layout_shape`: high-level hint, e.g. `"hero"`, `"stack"`, `"sidebar"`, `"grid"`, `"timeline"`.
   - `signals`: list of `attention_signal.id` assigned to this surface.

3. Treat surfaces as **outputs** of the layout planning stage, not inputs.

### 2.5 Layout Archetype

1. Define **layout archetypes** as named compositional patterns for a workspace (e.g. “dual pane”, “monitor wall”).
2. Implement at least the following archetypes in v1:

   - `FOCUS_METRIC`
     - A large hero metric or alert + supporting small panel(s).
   - `SCANNER_TABLE`
     - A main table/list with filters and summaries around it.
   - `DUAL_PANE_FLOW`
     - A list or table on one side, detail view on the other.
   - `MONITOR_WALL`
     - A grid of cards/KPIs designed for glanceable monitoring.

3. For each archetype, define:

   - A fixed set of **named surfaces/zones** (e.g. `primary`, `secondary`, `sidebar`, `footer`, `toolbar`).
   - Default **capacity** values for each surface (e.g. `primary.capacity = 0.7`, `secondary.capacity = 0.4`, etc.).
   - A default **layout_shape** per surface.

4. Serialize archetype definitions so they can be stored alongside or inside the layout engine config.

### 2.6 Layout Plan

1. Represent the **layout plan** as the main output of the layout engine.
2. Define at least the following fields:

   - `workspace_id`: string.
   - `persona_id`: string (persona actually used for computation).
   - `archetype`: string, one of the implemented layout archetypes.
   - `engine`: string identifying the layout engine variant (e.g. `"classic"`, `"dense"`, `"playful"`).
   - `surfaces`: array of surface objects (as in §2.4) with assigned `signals`.
   - `over_budget_signals`: optional list of attention signals that could not be placed within any surface capacity and are therefore relegated to tabs/drawers or navigation.

3. Make sure the layout plan is fully serializable as JSON and stable given the same inputs.

---

## 3. Processing Pipeline

Implement the following pipeline stages as pure, deterministic functions where possible.

### 3.1 From AppSpec to UI-Semantics IR

1. Implement a function (e.g. `build_ui_semantics_ir(app_spec)`):

   - Input: AppSpec or equivalent representation from DAZZLE’s core DSL.
   - Output: A structured object containing:
     - `workspaces`: list of workspace objects.
     - `personas`: list of persona objects.
     - `attention_signals`: list of attention signals, grouped by workspace.

2. Derive default `attention_weight` and other fields if missing:

   - If no weight provided, default to 0.5.
   - For primary resource for the workspace (e.g. main table), optionally auto-boost weight to 0.7–0.8.
   - If missing `urgency` or others, default to `"medium"` and `"occasional"` respectively.

3. Ensure no randomization is used at this stage; the mapping must be deterministic.

### 3.2 Persona-Aware Attention Adjustment

1. Implement a function (e.g. `adjust_attention_for_persona(workspace, persona)`):

   - Input: workspace + persona.
   - Operation:
     - For each attention signal in the workspace:
       - Compute `adjusted_weight = attention_weight * bias`, where `bias` may come from:
         - `persona.attention_biases[kind]`, if present.
         - Optional hard-coded rules (e.g. boost alerts for ops, boost KPIs for founders).
       - Clamp `adjusted_weight` to [0.0, 1.0].
   - Output: the same workspace with updated `attention_weight` values or a separate map of adjusted weights.

2. Keep the adjustment deterministic and based on clearly defined rules.

### 3.3 Archetype Selection

1. Implement a function (e.g. `select_archetype(workspace, persona)`) that chooses a layout archetype based on the semantic profile of attention signals.
2. Use deterministic rules, such as:

   - If there is exactly **one** `attention_signal` with `kind` in `{ "kpi", "alert-feed", "stat-card" }` and `attention_weight > 0.8`:
     - Select `FOCUS_METRIC`.
   - Else if there exists any `kind == "table"` or `"item-list"` and the total of these weights exceeds 0.5:
     - Select `SCANNER_TABLE`.
   - Else if there exists at least one `"item-list"` and at least one `"detail-view"`:
     - Select `DUAL_PANE_FLOW`.
   - Else:
     - Select `MONITOR_WALL`.

3. Allow for future extension of rules (e.g. ordering, explicit overrides), but avoid probabilistic behaviour.

### 3.4 Surface Allocation and Capacity Management

1. For each selected archetype, retrieve its set of surfaces and their capacities.
2. Implement a function (e.g. `assign_signals_to_surfaces(workspace, archetype_definition)`) that:

   - Sorts attention signals in descending order of `attention_weight`, optionally breaking ties by `urgency` and `interaction_frequency` (e.g. high urgency first, frequent interactions before rare).
   - Iterates through sorted signals and assigns them to surfaces using a deterministic strategy such as:
     1. Try to place the signal in the **primary** surface.
     2. If adding that signal would exceed `primary.capacity`, attempt to place it in `secondary`.
     3. If `secondary` is also at capacity, try `sidebar`, then other surfaces according to a defined order.
     4. If no surface can accommodate the signal within its capacity, add the signal to `over_budget_signals`.

3. Define capacity logic precisely:

   - Let `surface.load = sum(attention_weight of assigned signals)`.
   - Do not exceed `surface.capacity` if avoidable.
   - Optionally allow a small configurable tolerance (e.g. 0.05) for minor overflows, but keep rules explicit.

4. Ensure that the assignment algorithm is deterministic given the same inputs and sort order.

### 3.5 Over-Budget Handling

1. Any signal in `over_budget_signals` must still be represented in the UI, but via **collapsed structures** such as:

   - Tabs within a surface.
   - Accordions.
   - “More…” drawers.
   - Secondary navigation routes.

2. The **layout plan** itself should:

   - Explicitly list `over_budget_signals`.
   - Optionally annotate how they should be grouped (e.g. into a tab named `"More metrics"`).

3. For v1, it is sufficient to mark them as over-budget and annotate that they belong to a default “More” tab for the nearest appropriate surface.

### 3.6 Layout Plan Assembly

1. Implement a function (e.g. `build_layout_plan(workspace, persona, engine_variant)`) that orchestrates:

   - Persona-aware attention adjustment.
   - Archetype selection.
   - Surface allocation.
   - Over-budget handling.
   - Output of the final `LayoutPlan` object.

2. The function must be **pure and deterministic**:

   - Given the same workspace, persona, engine variant, archetype definitions, and capacity configuration, it must return the same layout plan.

---

## 4. Rendering Interface

### 4.1 Renderer Responsibilities

1. Implement a renderer interface that consumes `LayoutPlan` and produces a concrete UI (e.g. React components).
2. Require each renderer to:

   - Respect the archetype → grid/flex pattern mapping.
   - Map `surface.role` and `layout_shape` to container components (e.g. main content, sidebars, toolbars).
   - Map `attention_signal.kind` to component types:
     - `kpi`, `stat-card` → Stats component / Card with large number.
     - `alert-feed` → Alert list / notification stream.
     - `table`, `item-list` → Table or list component.
     - `detail-view` → Detail pane component.
     - `control-panel`, `filters` → Filter bar / control panel UI.
     - `task-list` → Checkable list / tasks component.
     - `form` → Form component.
     - `chart` → Chart wrapper.

3. Implement a default renderer variant (e.g. `"classic"`) that uses:

   - A minimal design system (e.g. Tailwind + headless components or Mantine).
   - Responsive layouts (e.g. 2-column dual pane collapses to stacked layout on mobile).

### 4.2 Example Layout Plan to Renderer Contract

1. Ensure that the renderer can consume an example layout plan of the form:

```json
{
  "workspace_id": "invoices_main",
  "persona_id": "ops_clerk",
  "archetype": "SCANNER_TABLE",
  "engine": "classic",
  "surfaces": [
    {
      "id": "primary",
      "role": "primary",
      "capacity": 0.7,
      "layout_shape": "stack",
      "signals": ["invoices_table"]
    },
    {
      "id": "secondary",
      "role": "secondary",
      "capacity": 0.4,
      "layout_shape": "hero",
      "signals": ["overdue_summary"]
    },
    {
      "id": "sidebar",
      "role": "peripheral",
      "capacity": 0.3,
      "layout_shape": "sidebar",
      "signals": ["filters"]
    }
  ],
  "over_budget_signals": []
}
```

2. Implement mapping logic that places:

   - `invoices_table` in the main content area.
   - `overdue_summary` in a prominent card above or near the table.
   - `filters` in a sidebar or collapsible panel.

---

## 5. Engine Variants and Extensibility

### 5.1 Engine Variants

1. Implement support for multiple **engine variants**, e.g.:

   - `"classic"`: conservative enterprise-style layout; generous whitespace.
   - `"dense"`: higher information density; more compact paddings and fonts.
   - `"playful"`: card-heavy, more expressive use of colour.

2. Keep the **UI-Semantics IR and Layout Plan format identical** across all engine variants.
3. Allow engine variants to vary only in:

   - Archetype implementations (different capacity profiles or surface compositions).
   - Component choice and styling in the renderer.

### 5.2 Adding New Archetypes

1. Provide a clear mechanism to add new archetypes:

   - Define surfaces, capacities, and shapes.
   - Add archetype selection rules.
   - Implement renderer mappings for new archetype surfaces.

2. Maintain backwards compatibility by:

   - Keeping default archetype definitions stable.
   - Versioning archetypes or engine configurations if necessary.

---

## 6. Testing and Determinism

### 6.1 Deterministic Behaviour

1. Ensure that no random numbers, time-based seeds, or external non-deterministic sources are used in the layout engine core.
2. Add tests that:

   - Provide a fixed workspace + persona + engine configuration.
   - Assert that repeated calls to `build_layout_plan(...)` produce identical JSON outputs.

### 6.2 Example Test Scenarios

1. **Single high-weight KPI:**

   - One KPI with `attention_weight = 0.9`.
   - One table with `attention_weight = 0.4`.
   - Expect archetype `FOCUS_METRIC` and KPI placed in `primary`.

2. **Table-dominant workspace:**

   - One table with `attention_weight = 0.7`.
   - One filter panel with `attention_weight = 0.3`.
   - Expect archetype `SCANNER_TABLE`, table in `primary`, filters in `sidebar` or `secondary`.

3. **Dual-pane scenario:**

   - One item list, one detail view, both moderate weight.
   - Expect archetype `DUAL_PANE_FLOW`, list and detail in different surfaces.

4. **Over-budget scenario:**

   - Many medium-weight signals such that `attention_budget` is exceeded.
   - Expect some signals in `over_budget_signals`, flagged for tab/drawer rendering.

---

## 7. Implementation Notes

1. Implement the layout engine in a cleanly separated module (e.g. `dazzle.ui.layout_engine`).
2. Prefer pure functions and immutable data structures where practical.
3. Keep the data model language-agnostic (i.e. easily serializable and usable from multiple runtimes).
4. Document all enums, kinds, and archetypes in code comments and/or a separate reference file so they can be surfaced to other DAZZLE tools and documentation.

---

## 8. DAZZLE Integration Details

### 8.1 Relationship to Existing DSL v0.2

The layout engine consumes the following from DAZZLE DSL v0.2:

**From `workspace` blocks**:
```dsl
workspace dashboard "Team Dashboard":
  purpose: "Real-time team overview"  # → maps to workspace.label

  urgent_tasks:
    source: Task                      # → becomes attention_signal
    filter: priority = high           # → informs attention_weight
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "No urgent tasks!"

  team_metrics:
    aggregate:                        # → becomes attention_signal (kind: kpi)
      total: count(Task)
      completed: count(Task where status = done)
```

**From `persona` variants in `ux` blocks**:
```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  ux:
    for admin:                        # → persona definition
      scope: all                      # → informs attention_biases
      purpose: "Full task management"
      action_primary: task_create

    for member:                       # → different persona
      scope: assigned_to = current_user
      purpose: "Your personal tasks"
      read_only: true
```

**From `attention` signals**:
```dsl
ux:
  attention critical:                 # → attention_signal with urgency: high
    when: due_date < today and status != done
    message: "Overdue task"
    action: task_edit

  attention warning:                  # → attention_signal with urgency: medium
    when: priority = high and status = todo
    message: "High priority - needs assignment"
```

### 8.2 New IR Extensions

Add to `src/dazzle/core/ir.py`:

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum

class TimeHorizon(str, Enum):
    REALTIME = "realtime"
    DAILY = "daily"
    ARCHIVAL = "archival"

class ProficiencyLevel(str, Enum):
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"

class SessionStyle(str, Enum):
    GLANCE = "glance"
    DEEP_WORK = "deep_work"

class AttentionSignalKind(str, Enum):
    KPI = "kpi"
    ALERT_FEED = "alert_feed"
    TABLE = "table"
    ITEM_LIST = "item_list"
    DETAIL_VIEW = "detail_view"
    TASK_LIST = "task_list"
    CONTROL_PANEL = "control_panel"
    CHART = "chart"
    STAT_CARD = "stat_card"
    FORM = "form"
    TIMELINE = "timeline"
    FILTERS = "filters"
    NAVIGATION = "navigation"

class AttentionSignal(BaseModel):
    """Semantic UI element requiring user awareness."""
    model_config = ConfigDict(frozen=True)

    id: str
    kind: AttentionSignalKind
    label: str
    source: str  # Reference to entity, surface, or data source
    attention_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency: Literal["low", "medium", "high"] = "medium"
    interaction_frequency: Literal["rare", "occasional", "frequent"] = "occasional"
    density_preference: Literal["compact", "comfortable"] = "comfortable"
    mode: Literal["read", "act", "configure"] = "read"
    constraints: dict[str, Any] = Field(default_factory=dict)

class WorkspaceLayout(BaseModel):
    """Extended workspace definition for layout engine."""
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    persona_targets: list[str] = Field(default_factory=list)
    attention_budget: float = Field(default=1.0, ge=0.0, le=1.5)
    time_horizon: TimeHorizon = TimeHorizon.DAILY
    engine_hint: Optional[str] = None
    attention_signals: list[AttentionSignal] = Field(default_factory=list)

class PersonaLayout(BaseModel):
    """Extended persona definition for layout engine."""
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    goals: list[str] = Field(default_factory=list)
    proficiency_level: ProficiencyLevel = ProficiencyLevel.INTERMEDIATE
    session_style: SessionStyle = SessionStyle.DEEP_WORK
    attention_biases: dict[str, float] = Field(default_factory=dict)
```

### 8.3 New Stack: `nextjs_semantic`

Create `src/dazzle/stacks/nextjs_semantic.py`:

**Purpose**: Generate Next.js application with semantically-aware layouts based on workspace definitions.

**Output Structure**:
```
build/nextjs_semantic/
├── app/
│   ├── layout.tsx                 # Root layout
│   ├── page.tsx                   # Home page
│   ├── workspaces/
│   │   ├── [workspace]/
│   │   │   └── page.tsx          # Dynamic workspace pages
│   │   └── layout_plans/
│   │       ├── dashboard.json    # Generated layout plans
│   │       └── tasks.json
│   └── components/
│       ├── surfaces/             # Surface components (Primary, Secondary, etc.)
│       ├── signals/              # Attention signal components (KPI, Table, etc.)
│       └── archetypes/           # Archetype templates
├── lib/
│   ├── layout-engine/
│   │   ├── types.ts              # TypeScript types for layout engine
│   │   ├── archetypes.ts         # Archetype definitions
│   │   ├── select-archetype.ts   # Archetype selection logic
│   │   └── allocate-signals.ts   # Surface allocation
│   ├── data/
│   │   └── api-client.ts         # Generated API client for backends
│   └── ui/                       # UI utilities
├── public/
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── next.config.js
```

**Key Features**:
1. Generates TypeScript layout engine based on spec
2. Creates React components for each archetype
3. Maps attention signals to component types
4. Includes responsive layouts and mobile support
5. Uses Tailwind CSS + Shadcn/UI or Mantine

**Integration Points**:
- Reads `workspace` definitions from AppSpec
- Reads `persona` variants from surfaces
- Reads `attention` signals from UX blocks
- Generates layout plans at build time (deterministic)
- Renders using layout plans at runtime (no computation needed)

### 8.4 CLI Integration

Add to `src/dazzle/cli.py`:

```python
@app.command()
def layout_plan(
    workspace: str = typer.Argument(
        ...,
        help="Workspace ID to generate layout plan for"
    ),
    persona: Optional[str] = typer.Option(
        None,
        "--persona",
        help="Persona to optimize layout for"
    ),
    engine: str = typer.Option(
        "classic",
        "--engine",
        help="Layout engine variant (classic, dense, playful)"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for layout plan JSON"
    )
):
    """Generate layout plan for a workspace."""
    from dazzle.ui.layout_engine import build_layout_plan
    from dazzle.core.manifest import load_manifest
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.parser import parse_modules
    from dazzle.core.linker import build_appspec

    manifest = load_manifest(Path.cwd() / "dazzle.toml")
    dsl_files = discover_dsl_files(Path.cwd(), manifest)
    modules = parse_modules(dsl_files)
    app_spec = build_appspec(modules, manifest.project_root)

    # Find workspace
    workspace_obj = next(
        (w for w in app_spec.workspaces if w.id == workspace),
        None
    )

    if not workspace_obj:
        typer.echo(f"Error: Workspace '{workspace}' not found", err=True)
        raise typer.Exit(1)

    # Find persona
    persona_obj = None
    if persona:
        persona_obj = next(
            (p for p in app_spec.personas if p.id == persona),
            None
        )
        if not persona_obj:
            typer.echo(f"Error: Persona '{persona}' not found", err=True)
            raise typer.Exit(1)

    # Generate layout plan
    plan = build_layout_plan(workspace_obj, persona_obj, engine)

    # Output
    import json
    plan_json = json.dumps(plan.model_dump(), indent=2)

    if output:
        output.write_text(plan_json)
        typer.echo(f"✅ Layout plan written to {output}")
    else:
        typer.echo(plan_json)
```

**Usage**:
```bash
# Generate layout plan for dashboard workspace
dazzle layout-plan dashboard

# Generate for specific persona
dazzle layout-plan dashboard --persona ops_clerk

# Generate and save to file
dazzle layout-plan dashboard --persona admin -o layout.json

# Use dense engine variant
dazzle layout-plan monitor_wall --engine dense
```

### 8.5 MCP Server Integration

Add layout planning tools to MCP server (`src/dazzle/mcp/server.py`):

```python
Tool(
    name="generate_layout_plan",
    description="Generate UI layout plan for a workspace with persona optimization",
    inputSchema={
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "Workspace ID to generate layout for"
            },
            "persona_id": {
                "type": "string",
                "description": "Persona to optimize layout for (optional)"
            },
            "engine": {
                "type": "string",
                "enum": ["classic", "dense", "playful"],
                "description": "Layout engine variant"
            }
        },
        "required": ["workspace_id"]
    }
),

Tool(
    name="preview_archetype",
    description="Preview which layout archetype would be selected for a workspace",
    inputSchema={
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "Workspace ID"
            }
        },
        "required": ["workspace_id"]
    }
),
```

### 8.6 Testing Strategy

**Unit Tests** (`tests/unit/test_layout_engine.py`):
- Test archetype selection with known workspace profiles
- Test signal allocation to surfaces
- Test capacity management and over-budget handling
- Test persona attention adjustment
- Test determinism (same inputs → same outputs)

**Integration Tests** (`tests/integration/test_nextjs_semantic.py`):
- Build complete Next.js app from DSL with workspaces
- Verify layout plans generated correctly
- Test React component generation
- Verify TypeScript types are correct

**Golden Master Tests** (`tests/integration/golden_masters/`):
- Store reference layout plans for example projects
- Assert new builds match golden masters exactly

### 8.7 Documentation Requirements

Create the following documentation:

1. **`docs/UI_SEMANTIC_LAYOUT.md`**
   - High-level overview of layout engine
   - How workspaces map to layouts
   - Archetype descriptions with diagrams
   - Persona influence on layouts

2. **`docs/ARCHETYPES_REFERENCE.md`**
   - Detailed description of each archetype
   - Surface definitions and capacities
   - When each archetype is selected
   - Visual examples (diagrams/mockups)

3. **`docs/stacks/NEXTJS_SEMANTIC.md`**
   - Stack-specific documentation
   - Generated file structure
   - Customization guide
   - Deployment instructions

4. **Update `docs/DAZZLE_DSL_REFERENCE.md`**
   - Document how `workspace` blocks influence layout
   - Document persona impact on UI
   - Add examples with layout outcomes

---

## 9. Implementation Roadmap

### Phase 1: Core Layout Engine (2-3 weeks)

**Week 1**: IR and Data Model
- [ ] Add layout IR types to `src/dazzle/core/ir.py`
- [ ] Implement `WorkspaceLayout`, `PersonaLayout`, `AttentionSignal`
- [ ] Add to IR documentation
- [ ] Unit tests for data model

**Week 2**: Layout Algorithm
- [ ] Implement archetype definitions
- [ ] Implement `select_archetype()` function
- [ ] Implement `assign_signals_to_surfaces()` function
- [ ] Implement `build_layout_plan()` orchestrator
- [ ] Determinism tests

**Week 3**: DSL Integration
- [ ] Parser support for workspace layout hints
- [ ] Parser support for persona layout attributes
- [ ] Map DSL attention signals to layout IR
- [ ] Integration tests

### Phase 2: Next.js Stack (2-3 weeks)

**Week 4**: Stack Generator
- [ ] Implement `nextjs_semantic` stack class
- [ ] Generate project structure
- [ ] Generate layout engine TypeScript code
- [ ] Generate layout plans at build time

**Week 5**: React Components
- [ ] Implement archetype templates
- [ ] Implement surface components
- [ ] Implement attention signal components
- [ ] Add Tailwind styling

**Week 6**: Polish & Testing
- [ ] Responsive layouts
- [ ] Mobile support
- [ ] Golden master tests
- [ ] Example projects

### Phase 3: Tooling & Documentation (1 week)

**Week 7**: CLI & MCP
- [ ] `dazzle layout-plan` command
- [ ] MCP server tools
- [ ] VS Code integration (preview layouts)
- [ ] Complete documentation

---

## 10. Success Criteria

**v0.3.0 is ready when**:

1. ✅ Layout engine generates deterministic layout plans
2. ✅ `nextjs_semantic` stack generates working Next.js apps
3. ✅ All 4 archetypes implemented and tested
4. ✅ Persona variants affect layout as expected
5. ✅ Over-budget signals handled gracefully
6. ✅ Documentation complete with examples
7. ✅ Golden master tests pass
8. ✅ Example projects demonstrate all archetypes
9. ✅ MCP tools available for layout planning
10. ✅ Zero random/stochastic behavior

