# DAZZLE Examples

A curated collection of example projects demonstrating DAZZLE's capabilities, organized by complexity level. Each example shows the complete journey from product specification to working application.

## Quick Start

```bash
cd examples/simple_task
dazzle serve
```

Open http://localhost:3000 to see the running app.

### Eval hub (multi-host local fleet)

Persistent catalogue under **`dazzle.local`** with per-app hosts
(`simple_task.dazzle.local`, …):

```bash
# monorepo root
.venv/bin/python scripts/example_hub/server.py --showcase-only
# → http://dazzle.local:9080/  (after DNS)
# → http://127.0.0.1:9080/    (no DNS)
```

See `scripts/example_hub/README.md` and
`archive/docs-superpowers/specs/2026-07-21-example-eval-hub-design.md`.

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

### Agent-first prove (journey + representation)

Examples are the **dogfood bar** for agent-first coding — not only “CRUD works”,
but *journey hubs*, *open-via hops*, and *representation integrity* so agents
don’t stop at warehouse-style lists (CyFuture pilot criticism).

```bash
# Fleet: every example with dazzle.toml
bash scripts/example_agent_prove.sh

# Single app
cd examples/simple_task
dazzle prove representation -p .
dazzle prove story --journey
dazzle agent wall -p . --markdown
dazzle agent playbook domain_data_shape
```

**Journey references (agent wall `executed_pass_journey`):**

| App | Hops / hubs | Bound stories |
|-----|-------------|---------------|
| **simple_task** | task → assignee overview; task hub + related discussion | ST-015 / 017 / 020 / 021 |
| **support_tickets** | ticket list → ticket hub + discussion; comments → ticket | ST-019 / 021 / 024 / 025 |

Warehouse-style lists alone are not enough — open-via + multi-section VIEW
hubs + `executed_by` bindings must prove green.

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

Four apps remain after flense ship E (ADR-0057); the other eight retired
because the consumer apps now prove their constructs. Each kept app is a probe.

| Level | Example | Key Concepts |
|-------|---------|--------------|
| 1. **Beginner** | [simple_task](simple_task/) | Entity basics, CRUD surfaces, workspaces, processes, LLM intents |
| 2. **Intermediate** | [support_tickets](support_tickets/) | Entity relationships (refs), `audit` construct, signing, SLA |
| 3. **Intermediate+** | [invoice_ops](invoice_ops/) | Tenancy + RLS, approvals, processes, services |
| 4. **Advanced** | [hr_records](hr_records/) | PII handling, org hierarchy, `process` |

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

### 2. Support Ticket System (Intermediate)

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
# Start from the minimal example (or run the MCP `bootstrap` tool on a SPEC.md)
cp -r examples/simple_task my_project
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
