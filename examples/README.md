# DAZZLE Examples

A curated collection of example projects demonstrating DAZZLE's capabilities, organized by complexity level. Each example shows the complete journey from product specification to working application.

## Quick Start

```bash
cd examples/simple_task
dazzle serve
```

Open http://localhost:3000 to see the running app.

### Stems

Every example carries a **`stems/`** directory: domain epistemic stems plus a
pointer to monorepo framework stems (`/stems/`) and HM stems when UI work
matters. New-app template notes: monorepo `stems/app-template/`. Agents:
reconstruct domain judgement from `stems/INDEX.md` before expanding the DSL.
Gate: `tests/unit/test_stems_layout.py`.

### Privacy / data-protection pack (SaaS legal pages)

Every example ships a public `sitespec.yaml` with de-facto SaaS legal routes
(`/privacy`, `/cookies`, `/terms`) and a **compliance pack** derived from DSL
`pii()` annotations:

```bash
cd examples/<app>
dazzle compliance privacy -o docs/privacy
# → docs/privacy/{privacy_policy,cookie_policy,ropa}.md
# → site/content/legal/{privacy,cookies}.md  (always refreshed)
# → site/content/legal/terms.md              (scaffold if missing)
```

Footer **Legal** links Privacy / Cookies / Terms. ROPA stays pack-only
(Art. 30 controller record). Terms use the framework SaaS template (brand
substituted) — edit freely; re-runs do not overwrite an existing terms.md.
See `support_tickets` for the fullest walkthrough.

### HM surfaces (HaTchi-MaXchi)

Example UIs are **HM-shaped**: pages compose Hyperparts (see ADR-0053), not
hand-rolled Alpine/Tailwind. Live emit is pure `dz-*` / `data-dz-*` markup.

```bash
# Rebuild every example and score for pre-HM residuals (Alpine / dead TW)
python scripts/example_hm_surface_audit.py
python scripts/example_hm_surface_audit.py --status   # one-line for logs
```

`examples/*/dnr-ui/` is **gitignored** local preview output from
`dazzle build-ui`. Never treat a stale `dnr-ui/` tree as the product surface —
regenerate or run the audit. This is what makes the fleet accessible to
`/improve` tooling (dual-lock, contracts, visual_tier2) without false
"non-HM example" noise.

---

## Learning Path

The examples are organized in a progressive learning sequence. Each builds on concepts from the previous level.

### Learning sequence

| Level | Example | Key Concepts |
|-------|---------|--------------|
| 1. **Beginner** | [simple_task](simple_task/) | Entity basics, CRUD surfaces, workspaces, attention signals |
| 2. **Beginner+** | [contact_manager](contact_manager/) | DUAL_PANE_FLOW archetype, signal weighting, list+detail pattern |
| 3. **Intermediate** | [support_tickets](support_tickets/) | Entity relationships (refs), indexes, multi-entity surfaces |
| 4. **Intermediate+** | [ops_dashboard](ops_dashboard/) | Personas, COMMAND_CENTER archetype, engine hints |
| 5. **Advanced** | [fieldtest_hub](fieldtest_hub/) | Complex domain, persona scoping, access rules, attention signals |

### Topic-focused demos

These apps each foreground one capability rather than building toward a complete domain. Use them as live references when you reach for a specific construct.

| Demo | Showcases |
|------|-----------|
| [project_tracker](project_tracker/) | PM domain + rich form widgets (combobox/tags/date) on HM Hyperparts |
| [design_studio](design_studio/) | Color pickers, rich text, asset management |
| [llm_ticket_classifier](llm_ticket_classifier/) | LLM intents (classification + extraction) with deterministic-first integration |
| [invoice_ops](invoice_ops/) | Invoice workflow keystone — processes, events, services |
| [acme_billing](acme_billing/) | Multi-tenant billing domain + RBAC / compliance fixtures |
| [hr_records](hr_records/) | Personnel records / org chart |
| [domain_join_co](domain_join_co/) | Verified domain-join onboarding flow |

---

## Example Details

### 1. Simple Task Manager (Beginner)

**Location**: [`simple_task/`](simple_task/)

A personal task management app - the recommended starting point for learning DAZZLE.

**What You'll Learn**:
- Entity definition with various field types
- All four surface modes (list, view, create, edit)
- UX blocks (purpose, sort, filter, search, empty)
- Attention signals (warning, notice)
- Workspace composition with metrics and filtered regions

**Quick Start**:
```bash
cd simple_task && dazzle serve
```

---

### 2. Contact Manager (Beginner+)

**Location**: [`contact_manager/`](contact_manager/)

A contacts application demonstrating the list+detail pattern.

**What You'll Learn**:
- DUAL_PANE_FLOW archetype (master-detail layout)
- Signal weighting for layout selection
- Workspace with paired signals

**Quick Start**:
```bash
cd contact_manager && dazzle serve
```

---

### 3. Support Ticket System (Intermediate)

**Location**: [`support_tickets/`](support_tickets/)

A multi-entity support system with user, ticket, and comment relationships.

**What You'll Learn**:
- Entity relationships with `ref` fields
- Required vs optional references
- Database indexes for performance
- Multiple surfaces per entity
- Cross-entity navigation

**Quick Start**:
```bash
cd support_tickets && dazzle serve
```

---

### 4. Operations Dashboard (Intermediate+)

**Location**: [`ops_dashboard/`](ops_dashboard/)

A real-time operations monitoring dashboard for DevOps teams.

**What You'll Learn**:
- Persona definition with proficiency levels
- COMMAND_CENTER archetype for expert users
- Engine hints for layout control
- Dense, information-rich interfaces

**Quick Start**:
```bash
cd ops_dashboard && dazzle serve
```

---

### 5. FieldTest Hub (Advanced)

**Location**: [`fieldtest_hub/`](fieldtest_hub/)

A complex hardware field testing platform with multiple user roles.

**What You'll Learn**:
- 6-entity domain model with relationships
- Persona-aware surface scoping (`for engineer`, `for tester`)
- Access rules for data visibility
- Complex filtering and aggregations
- Real-world workflow modeling

**Quick Start**:
```bash
cd fieldtest_hub && dazzle serve
```

---

## Example Structure

Each example follows a consistent structure:

```
example_name/
├── SPEC.md              # Product specification (refined requirements)
├── README.md            # Example documentation
├── dazzle.toml          # Project configuration
├── dsl/
│   └── app.dsl          # DAZZLE DSL definition
└── testspec.json        # Generated test specification (if present)
```

### The Specification Journey

```
SPEC.md          →  Human-readable requirements
    ↓                (refined through LLM collaboration)
dsl/app.dsl      →  DAZZLE DSL implementation
    ↓                (declarative, stack-agnostic)
Dazzle Runtime      →  Live application
    ↓                (no code generation needed)
E2E Tests        →  Automated validation
                     (generated from spec)
```

---

## Running Examples

### Start an Example
```bash
cd examples/<name>
dazzle serve
```

### Validate DSL
```bash
dazzle validate
```

### Generate Test Specification
```bash
dazzle test generate
```

### Run E2E Tests
```bash
dazzle test run
```

---

## DSL Quick Reference

### Entity Definition
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add
```

### Surface Definition
```dsl
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"

  ux:
    purpose: "View all tasks"
    sort: created_at desc
    filter: status
```

### Workspace Definition
```dsl
workspace dashboard "Dashboard":
  purpose: "Overview with metrics"

  metrics:
    source: Task
    aggregate:
      total: count(Task)
```

### Attention Signal
```dsl
ux:
  attention warning:
    when: due_date < today and status != done
    message: "Overdue"
```

---

## Archived Examples

Additional examples are available in `_archive/` for reference:
- `uptime_monitor` - FOCUS_METRIC archetype demo
- `inventory_scanner` - SCANNER_TABLE archetype demo
- `email_client` - MONITOR_WALL archetype demo
- `urban_canopy` - Volunteer tree monitoring
- `archetype_showcase` - All 5 archetypes in one project

These were consolidated to focus the learning path on the 5 core examples.

---

## Creating Your Own

```bash
# Initialize a new project
dazzle init my_project
cd my_project

# Edit the DSL
vim dsl/app.dsl

# Validate
dazzle validate

# Run
dazzle serve
```

---

## Getting Help

- **Documentation**: See `docs/` directory
- **DSL Reference**: `docs/DAZZLE_DSL_QUICK_REFERENCE.md`
- **Issues**: https://github.com/anthropics/dazzle/issues

---

*Part of the DAZZLE project - DSL-first application development.*
