# Related Display Intent

**Date:** 2026-03-28
**Status:** Approved
**Predecessor:** IR Triple Enrichment (v0.50.0)

## Problem

The framework's detail page renders all related entities as uniform tabs with tables. The DSL declares relationships (`ref Entity`) but doesn't express **how to present related entities in context**. Two projects exposed this gap from different angles:

- **AegisMark** (education, 9 entities): Built a custom `detail_view.html` override for Manuscript — a PDF viewer with slide-in panels for MarkingResult and ManuscriptFeedback. The framework couldn't express "show these as side panels."

- **CyFuture** (accountancy, 51 entities): Contact has 31 related entities shown as 31 equal tabs. A human would group them: Compliance (status cards), Onboarding (table), Documents (file list). The framework couldn't express grouping or per-group display modes.

The triple (v0.50.0) knows which related entities each persona can access. The missing piece is **display intent** — how those related entities should be grouped and presented.

## DSL Syntax

New `related` block, peer of `section` and `action`, valid only on `mode: view` surfaces:

```dsl
surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view

  section main "Contact Information":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"

  related compliance "Compliance":
    display: status_cards
    show: SelfAssessmentReturn, VATReturn, ComplianceDeadline

  related onboarding "Onboarding":
    display: table
    show: OnboardingFlow, OnboardingChecklist

  related documents "Documents":
    display: file_list
    show: Document, EngagementLetter
```

### Rules

- `related` blocks are peers of `section` and `action` inside a surface
- Only valid on `mode: view` surfaces (link-time error)
- `display:` is required — forces the agent to declare intent explicitly
- `show:` takes a comma-separated list of entity names
- Declaration order = render order
- `related` blocks are optional — surfaces without them behave exactly as today

### Display Modes (closed enum)

| Mode | Description | Use case |
|------|-------------|----------|
| `table` | Tabbed tables (current framework behavior) | Generic related entities |
| `status_cards` | Grid of cards with status badge + key fields | Tax returns, compliance deadlines |
| `file_list` | Compact rows with file icon, name, date, download link | Documents, evidence, letters |

Future modes (`progress`, `side_panel`, `inline`) are documented but not implemented. The parser rejects unknown mode strings — adding a mode is a deliberate framework decision (new enum value + new fragment template).

### Ungrouped Entity Behavior (Option 3: Hybrid)

When a surface has `related` blocks, entities **not** mentioned in any group auto-collect into a default "Other" group with `display: table` at the bottom. This means:

- **No `related` blocks:** All reverse-FK entities appear as individual tabs (identical to current behavior)
- **Some `related` blocks:** Named entities render with their declared display mode; remaining entities appear in "Other"
- **All entities grouped:** No "Other" group rendered

This is safe for agents — nothing is hidden by accident. The "Other" group signals "these exist but haven't been given display intent yet" and can be flagged by discovery/audit tools.

## IR Model

### New Types (`src/dazzle/core/ir/surfaces.py`)

```python
class RelatedDisplayMode(StrEnum):
    """Display modes for related entity groups on detail pages."""
    TABLE = "table"
    STATUS_CARDS = "status_cards"
    FILE_LIST = "file_list"


class RelatedGroup(BaseModel):
    """A named group of related entities with a shared display mode.

    Attributes:
        name: Group identifier (DSL name, e.g. "compliance")
        title: Human-readable label (e.g. "Compliance")
        display: How to render the group's entities
        show: Entity names to include (validated at link time)
    """
    name: str
    title: str | None = None
    display: RelatedDisplayMode
    show: list[str]

    model_config = ConfigDict(frozen=True)
```

### SurfaceSpec Extension

```python
class SurfaceSpec(BaseModel):
    # ... existing fields ...
    related_groups: list[RelatedGroup] = Field(default_factory=list)
```

### Triple Integration

`VerifiableTriple` gets a new field:

```python
related_groups: list[str] = Field(default_factory=list)  # group names
```

Contracts verify that the detail page renders the expected groups for each persona. Group names are sufficient — display mode and entity list are in the IR.

## Link-Time Validation

Validation requires the full domain model (not possible at parse time):

1. **Entity existence:** Each entity in `show:` must exist in the domain — error: "Unknown entity 'Foo' in related group 'bar'"
2. **FK path:** Each entity in `show:` must have a reverse FK (direct or polymorphic) to the surface's `entity_ref` — error: "Entity 'Foo' has no FK path to 'Contact' in related group 'bar'"
3. **No duplicates:** An entity cannot appear in multiple groups on the same surface — error: "Entity 'Foo' appears in both 'compliance' and 'documents'"
4. **View mode only:** `related` blocks on non-`view` surfaces — error: "related blocks are only valid on mode: view surfaces"

## Template Context

### New Model (`template_context.py`)

```python
class RelatedGroupContext(BaseModel):
    """A group of related entity tabs with a shared display mode."""
    group_id: str              # DOM id (e.g. "group-compliance")
    label: str                 # "Compliance"
    display: str               # "table", "status_cards", "file_list"
    tabs: list[RelatedTabContext]  # Individual entities in this group
    is_auto: bool = False      # True for the auto-generated "Other" group
```

### DetailContext Change

```python
class DetailContext(BaseModel):
    # Replace: related_tabs: list[RelatedTabContext]
    related_groups: list[RelatedGroupContext] = Field(default_factory=list)
```

This is a breaking change to the context model but only affects framework-owned templates — no user code consumes `DetailContext` directly.

## Template Compiler

The existing `_reverse_refs` / `_poly_refs` scan in `_compile_view_surface()` stays unchanged. After building the flat `RelatedTabContext` list, a new grouping step:

1. If the surface has `related_groups` in the IR, iterate them. For each group, pull matching tabs from the flat list by entity name, wrap in `RelatedGroupContext` with the declared display mode.
2. Remaining tabs not claimed by any group → `RelatedGroupContext(label="Other", display="table", is_auto=True)`.
3. If the surface has no `related_groups`, all tabs go into a single auto group with `is_auto=True`.

## Template Rendering

### detail_view.html

The current flat tab loop becomes a two-level dispatch:

```html
{% for group in detail.related_groups %}
<div class="mt-6" data-dazzle-related-group="{{ group.group_id }}">
  {% if detail.related_groups | length > 1 %}
    <h3 class="text-lg font-semibold mb-3">{{ group.label }}</h3>
  {% endif %}

  {% if group.display == "table" %}
    {% include "fragments/related_table_group.html" %}
  {% elif group.display == "status_cards" %}
    {% include "fragments/related_status_cards.html" %}
  {% elif group.display == "file_list" %}
    {% include "fragments/related_file_list.html" %}
  {% endif %}
</div>
{% endfor %}
```

### Fragment Templates

- **`related_table_group.html`**: The existing tab-switching code (Alpine + table), extracted from the current `detail_view.html`. No behavior change.
- **`related_status_cards.html`**: CSS grid of cards. Each card shows entity title, status badge (from status/state field), key fields. Clickable to detail page. Same `hx-get` lazy-load pattern as table tabs.
- **`related_file_list.html`**: Compact list rows with file icon, name, date column, download link. Suited for entities with `file` type fields.

All fragments receive `RelatedTabContext` data (columns, rows, api_endpoint). They render the same data differently. No new API endpoints needed.

## Parser

### Lexer

New token: `RELATED` (keyword).

### Surface Parser (`surface.py`)

New branch in `parse_surface()`:

```python
elif self.match(TokenType.RELATED):
    group = self._parse_related_group()
    related_groups.append(group)
```

`_parse_related_group()` parses the `related name "title":` header, then `display:` and `show:` lines inside the indented block. Same structural pattern as `_parse_surface_access()`.

## What This Does NOT Change

- **API endpoints** — no new routes; same `/api/{entity}` endpoints serve all display modes
- **Runtime routes** — same detail page route, richer context
- **Auth/RBAC** — persona visibility still from triples + `visible_condition`
- **Existing apps** — surfaces without `related` blocks behave identically to today

## Testing Strategy

- **Parser tests** (`test_parser.py`): Parse surfaces with `related` blocks; verify IR `RelatedGroup` list with correct names, display modes, entity lists
- **Linker validation tests**: Missing entity, missing FK, duplicate entity across groups, `related` on non-view surface — all produce expected errors
- **Template compiler tests**: Surface with groups produces `RelatedGroupContext`; surface without groups produces auto "Other" group; mixed surfaces group correctly
- **Template rendering tests**: Detail page with groups renders correct DOM structure — group headers, mode-specific fragments, "Other" group for ungrouped entities

## Future Work

- **Display modes:** `progress` (stepper for multi-step flows), `side_panel` (AegisMark-style slide-in panels), `inline` (single related record shown inline for 1:1 relationships)
- **Per-group field projection:** `show: SelfAssessmentReturn(status, due_date)` — select which columns to display per entity within a group
- **Discovery integration:** Flag "Other" group entities as display-intent gaps in discovery reports
