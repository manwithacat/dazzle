# Capability Discovery Design

**Date**: 2026-03-28
**Status**: Approved
**Goal**: Surface relevant Dazzle capabilities to agents at decision points using contextual references to working examples, without anchoring toward specific decisions.

## Context

Dazzle v0.51.x added 35 UX components, 4 vendored libraries, and `widget=` DSL syntax. Agents working with existing apps don't know these capabilities exist — they build with the patterns they've seen before. The goal is a system that shows agents *what's possible* by referencing working examples, letting them reason about applicability independently.

## Design Principles

1. **Contextual, not prescriptive** — show what exists and where it's demonstrated, never tell the agent what to do
2. **Example-driven** — every capability reference points to a real working app with a file and line number
3. **Non-anchoring** — the language is "relevance" not "suggestion" or "recommendation"
4. **Distributed rules, coordinated output** — each domain owns its pattern matching, a thin engine coordinates
5. **KG-documented** — agents can pull-discover capabilities via knowledge graph queries

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Consumers (lint, bootstrap, MCP analyze)       │
│  Call suggest_capabilities(appspec) → Relevance │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│  Suggestion Engine (coordinator)                │
│  src/dazzle/core/capability_discovery.py        │
│  Calls domain rule modules, builds example refs │
└──────────────────┬──────────────────────────────┘
                   │ calls
┌──────────────────▼──────────────────────────────┐
│  Rule Modules (distributed, own their domain)   │
│  widget_rules.py   — field→widget opportunities │
│  layout_rules.py   — surface→workspace patterns │
│  component_rules.py — alpine component relevance│
│  completeness_rules.py — missing CRUD surfaces  │
│  All in src/dazzle/core/discovery/              │
└──────────────────┬──────────────────────────────┘
                   │ references
┌──────────────────▼──────────────────────────────┐
│  Knowledge Graph (documentation layer)          │
│  capabilities.toml seeded into KG               │
│  Agents query via knowledge(operation=concept)  │
└──────────────────┬──────────────────────────────┘
                   │ indexed from
┌──────────────────▼──────────────────────────────┐
│  Example Index (built at scan time)             │
│  Scans example apps for demonstrated caps       │
│  Maps capability_key → list[ExampleRef]         │
└─────────────────────────────────────────────────┘
```

## The Relevance Model

```python
@dataclass(frozen=True)
class ExampleRef:
    """A reference to a capability demonstrated in an example app."""
    app: str           # e.g., "project_tracker"
    file: str          # e.g., "dsl/app.dsl"
    line: int          # e.g., 152
    context: str       # e.g., 'field description "Description" widget=rich_text'

@dataclass(frozen=True)
class Relevance:
    """A contextual reference to a Dazzle capability that may be applicable."""

    # What was observed in the current app
    context: str          # e.g., "field 'description' (text) on surface 'task_create'"

    # What capability exists
    capability: str       # e.g., "widget=rich_text"
    category: str         # e.g., "widget", "layout", "component", "completeness"

    # Where it's demonstrated
    examples: list[ExampleRef]  # Non-empty; at least one working reference

    # Knowledge graph entity for deeper exploration
    kg_entity: str        # e.g., "capability:widget_rich_text"
```

No `reason`, `recommendation`, or `severity` fields. The agent sees: here's what you have, here's what exists, here's where it works.

## Rule Modules

### `widget_rules.py`

Scans create/edit surfaces for fields with widget-capable types but no `widget=` annotation.

| Field pattern | Relevant capability | Match logic |
|--------------|-------------------|-------------|
| `text` field, no widget | `widget=rich_text` | `field.type.kind == TEXT and not widget` |
| `ref` field, no widget, no source | `widget=combobox` | `field.type.kind == REF and not widget and not source` |
| `str` field, name matches `*tag*\|*label*\|*keyword*` | `widget=tags` | Name pattern match |
| `date`/`datetime` field, no widget | `widget=picker` | `field.type.kind in (DATE, DATETIME) and not widget` |
| `str(7)` field, name matches `*color*` | `widget=color` | `max_length == 7 and name pattern` |
| `int` field, name matches `*score*\|*rating*\|*priority*\|*level*` | `widget=slider` | Name pattern match |

Only fires for `mode: create` and `mode: edit` surfaces (widgets are no-ops on view/list).

### `layout_rules.py`

Scans entities and surfaces for structural patterns.

| Pattern | Relevant capability |
|---------|-------------------|
| Entity with `transitions:` block but no kanban workspace region | Kanban display mode |
| Entity with `date` fields but no timeline workspace region | Timeline display mode |
| Detail surface with 3+ related entities, no `related` groups | Related group display modes (table, status_cards, file_list) |
| Create/edit surface with 5+ fields, single section | Multi-section form (wizard stepper) |

### `component_rules.py`

Identifies Alpine/HTMX interactive component relevance.

| Pattern | Relevant capability |
|---------|-------------------|
| App with 5+ surfaces, no command palette fragment reference | `dzCommandPalette` (Cmd+K navigation) |
| Detail surfaces that could benefit from slide-over panels | `dzSlideOver` for side panel detail |
| Entity with `enum` status field + grid workspace display | Toggle group for view filtering |

### `completeness_rules.py`

Identifies structural gaps in CRUD coverage.

| Pattern | Relevant capability |
|---------|-------------------|
| Entity with `update` permit but no `mode: edit` surface | Missing edit surface |
| Entity with `list` permit but no `mode: list` surface | Missing list surface |
| Entity with `delete` permit but no delete action visible on any surface | Missing delete workflow |
| Entity with no surfaces at all | Unreachable entity |

## Example Index

Built at scan time by parsing example apps (cheap — reuses existing DSL parsing).

```python
def build_example_index(examples_dir: Path) -> dict[str, list[ExampleRef]]:
    """Scan example apps and index which capabilities they demonstrate.

    For each example app:
    - Parse the AppSpec
    - For each surface field with widget=, record (app, file, line, context)
    - For each workspace with kanban/timeline/grid, record the same
    - For each related group, record the same
    - For each multi-section form, record the same

    Returns: capability_key → list[ExampleRef]
    """
```

The index maps capability keys (e.g., `"widget_rich_text"`, `"layout_kanban"`, `"component_command_palette"`) to lists of `ExampleRef`. The suggestion engine joins rule module output with this index to produce `Relevance` objects with concrete example references.

**Fallback**: If the examples directory is not available (e.g., PyPI install without examples), the engine still produces relevance items but with empty `examples` lists and a generic `kg_entity` reference.

## Knowledge Graph Seeding

New TOML file: `src/dazzle/mcp/semantics_kb/capabilities.toml`

```toml
[meta]
category = "UX Capabilities"
version = "0.51.9"

[[entries]]
id = "widget_rich_text"
type = "capability"
definition = "Rich text editing via Quill v2 for formatted content"
syntax = 'field description "Description" widget=rich_text'
applies_to = "text fields on create/edit surfaces"
demonstrated_in = ["project_tracker", "design_studio", "component_showcase"]

[[entries]]
id = "widget_combobox"
type = "capability"
definition = "Searchable single-select via Tom Select for entity references"
syntax = 'field assigned_to "Assignee" widget=combobox'
applies_to = "ref fields on create/edit surfaces"
demonstrated_in = ["project_tracker", "design_studio", "component_showcase"]

# ... one entry per capability (widgets, layout modes, components)
```

**Relations seeded:**
- `capability:widget_rich_text` → `demonstrated_in` → `example:project_tracker`
- `capability:widget_rich_text` → `applies_to` → `concept:text_field`
- `capability:layout_kanban` → `demonstrated_in` → `example:project_tracker`
- `capability:component_command_palette` → `demonstrated_in` → `example:project_tracker`

**KG version bump:** `ensure_seeded()` checks seed version — bump when capabilities.toml changes.

Agents querying `knowledge(operation='concept', term='widget_rich_text')` get back the capability definition, syntax, and example app references.

## Consumer Integration

### 1. `dazzle lint` / `dsl operation=lint`

Appends relevance items after errors and warnings:

```
Validation passed (3 entities, 8 surfaces, 2 workspaces)

Errors: 0  Warnings: 2

Relevant capabilities (6):
  task_create.description (text) — widget=rich_text in project_tracker/dsl/app.dsl:152
  task_create.assigned_to (ref User) — widget=combobox in project_tracker/dsl/app.dsl:154
  task_create.due_date (date) — widget=picker in project_tracker/dsl/app.dsl:158
  task_detail has 4 related entities — related groups in project_tracker/dsl/app.dsl:180
  Task has transitions but no kanban workspace — kanban display in project_tracker/dsl/app.dsl:120
  Task has update permit but no edit surface — task_edit in project_tracker/dsl/app.dsl:195
```

**MCP format** (for `dsl operation=lint`): returned as `relevance` list alongside `errors` and `warnings` in the JSON response.

### 2. `bootstrap`

The mission briefing gains a `relevant_capabilities` section. When bootstrap discovers entities with text fields, date fields, ref fields, etc., it references how example apps handle similar patterns. This primes the agent's DSL generation without prescribing specific choices.

### 3. MCP `knowledge`

Pull-based discovery. Agents query the KG for capabilities they're curious about. The seeded capability entities have `demonstrated_in` relations pointing to example apps, so agents get concrete references.

### 4. Quiet mode

`--quiet` flag or `suppress_relevance=true` on MCP calls suppresses relevance output. When all fields already have widgets and all surfaces are complete, the list is empty and nothing is shown.

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/core/discovery/__init__.py` | Create | Package init, exports `suggest_capabilities` |
| `src/dazzle/core/discovery/engine.py` | Create | Coordinator — calls rule modules, joins with example index |
| `src/dazzle/core/discovery/models.py` | Create | `Relevance`, `ExampleRef` dataclasses |
| `src/dazzle/core/discovery/widget_rules.py` | Create | Widget annotation relevance rules |
| `src/dazzle/core/discovery/layout_rules.py` | Create | Workspace/surface layout relevance rules |
| `src/dazzle/core/discovery/component_rules.py` | Create | Alpine/HTMX component relevance rules |
| `src/dazzle/core/discovery/completeness_rules.py` | Create | CRUD completeness relevance rules |
| `src/dazzle/core/discovery/example_index.py` | Create | Scans example apps, builds capability→ExampleRef index |
| `src/dazzle/mcp/semantics_kb/capabilities.toml` | Create | KG seed data for capabilities |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Modify | Seed capabilities.toml into KG |
| `src/dazzle/core/lint.py` | Modify | Add relevance output to lint pipeline |
| `src/dazzle/cli/project.py` | Modify | Display relevance items in CLI output |
| `src/dazzle/mcp/server/handlers/dsl/validate.py` | Modify | Include relevance in lint MCP response |
| `src/dazzle/mcp/server/handlers/bootstrap.py` | Modify | Add relevant_capabilities to mission briefing |
| `tests/unit/test_capability_discovery.py` | Create | Tests for engine + rule modules |
| `tests/unit/test_example_index.py` | Create | Tests for example scanning |

## Testing

**Unit tests per rule module:**
- Known AppSpec → expected Relevance items
- Fully-annotated AppSpec (component_showcase) → empty or near-empty list
- No applicable patterns → empty list

**Integration tests:**
- `suggest_capabilities()` against `examples/simple_task` (no widgets) → produces widget relevance items
- Against `examples/component_showcase` (fully loaded) → produces few or none
- Against `examples/project_tracker` → no widget relevance for annotated fields

**KG tests:**
- `knowledge(operation='concept', term='widget_rich_text')` returns capability with example refs

**Regression test:**
- Cross-check: every key in `_WIDGET_MAP` (triples.py) has a corresponding entry in capabilities.toml and a rule in widget_rules.py. New widget types without all three fail the test.

**Example coverage test:**
- Every capability in capabilities.toml is demonstrated in at least 2 example apps (matches the coverage matrix from the UX component expansion spec).
