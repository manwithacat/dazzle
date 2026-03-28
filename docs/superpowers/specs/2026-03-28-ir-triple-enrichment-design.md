# IR Triple Enrichment — Design Spec

**Date:** 2026-03-28
**Status:** Approved
**Prerequisite:** ADR-0019 (Surface Triple as Atomic Unit of Verifiable Behavior)
**Replaces:** Empirical triple derivation in `contracts.py`

## Problem

The UX contract verification system (v0.49.14) derives (Entity, Surface, Persona) triples empirically by fetching rendered HTML and reverse-engineering what the template engine produced. This works — 121/121 on fieldtest_hub — but is:

- **Slow**: requires a running server to derive triples
- **Fragile**: the contract generator had to learn FK widget resolution, persona routing, and surface mode gates through 3 convergence cycles
- **Duplicative**: the information already exists across the parser, linker, and template engine — it's just not assembled in one place

## Solution

Enrich the AppSpec IR to cache derived triples at link time. Downstream consumers (contract verification, validation, compliance) read them directly instead of re-deriving from HTML.

**Approach:** Eager computation in the linker (step 10b), stored as `triples: list[VerifiableTriple]` on AppSpec. Contract generation becomes a thin mapper over IR triples.

## Data Models

New file: `src/dazzle/core/ir/triples.py`

### WidgetKind

```python
class WidgetKind(StrEnum):
    TEXT_INPUT = "text_input"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    DATE_PICKER = "date_picker"
    DATETIME_PICKER = "datetime_picker"
    NUMBER_INPUT = "number_input"
    EMAIL_INPUT = "email_input"
    ENUM_SELECT = "enum_select"
    SEARCH_SELECT = "search_select"
    MONEY_INPUT = "money_input"
    FILE_UPLOAD = "file_upload"
```

### SurfaceFieldTriple

Per-field rendering resolution for a surface:

```python
class SurfaceFieldTriple(BaseModel, frozen=True):
    field_name: str
    widget: WidgetKind
    is_required: bool
    is_fk: bool
    ref_entity: str | None = None
```

### SurfaceActionTriple

Per-surface action with permission requirement:

```python
class SurfaceActionTriple(BaseModel, frozen=True):
    action: str              # "list", "create_link", "edit_link", "delete_button", "transition:{name}"
    requires_permission: str  # "LIST", "CREATE", "UPDATE", "DELETE"
    visible_to: list[str]     # persona IDs
```

### VerifiableTriple

The atomic unit — one per (entity, surface, persona) combination:

```python
class VerifiableTriple(BaseModel, frozen=True):
    entity: str
    surface: str
    persona: str
    surface_mode: str             # "list", "view", "create", "edit"
    actions: list[str]            # actions this persona can perform on this surface
    fields: list[SurfaceFieldTriple]
```

`SurfaceActionTriple` is per-surface (shared across personas). `VerifiableTriple` is per-persona and flattens the action list to just action names, avoiding duplication of the full action manifest.

## Derivation Rules

### Widget Resolution

Pure mapping from `FieldTypeKind` to `WidgetKind`, mirroring `_field_type_to_form_type()` in `template_compiler.py:149`:

```python
_WIDGET_MAP: dict[FieldTypeKind, WidgetKind] = {
    FieldTypeKind.BOOL: WidgetKind.CHECKBOX,
    FieldTypeKind.DATE: WidgetKind.DATE_PICKER,
    FieldTypeKind.DATETIME: WidgetKind.DATETIME_PICKER,
    FieldTypeKind.INT: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.DECIMAL: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.MONEY: WidgetKind.MONEY_INPUT,
    FieldTypeKind.TEXT: WidgetKind.TEXTAREA,
    FieldTypeKind.EMAIL: WidgetKind.EMAIL_INPUT,
    FieldTypeKind.ENUM: WidgetKind.ENUM_SELECT,
    FieldTypeKind.REF: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.BELONGS_TO: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.FILE: WidgetKind.FILE_UPLOAD,
}
```

Additional rules:
- Default (not in map): `WidgetKind.TEXT_INPUT`
- `_id` suffix convention: `WidgetKind.SEARCH_SELECT` (matches `contracts.py:324`)
- Surface element `source=` option: override to `WidgetKind.SEARCH_SELECT`

### Action Derivation

| Surface mode | Actions generated |
|---|---|
| `list` | `list`, `detail_link`, `create_link` (if CREATE permitted) |
| `view` | `edit_link` (if UPDATE permitted AND edit surface exists), `delete_button` (if DELETE permitted), `transition:{name}` (from state machine) |
| `create` | `create_submit` |
| `edit` | `edit_submit` |

### Triple Assembly

```
for each entity (skip _FRAMEWORK_ENTITIES):
    for each surface referencing entity:
        resolve fields → list[SurfaceFieldTriple]
        resolve actions → list[SurfaceActionTriple]
        for each persona:
            filter actions by persona permissions
            if persona has ANY permitted action:
                emit VerifiableTriple(entity, surface, persona, mode, filtered_actions, fields)
```

### Permission Helpers

The following functions move from `contracts.py` to `triples.py`:

- `_condition_matches_role(condition, role)` — check if a ConditionExpr contains a role_check
- `_condition_is_pure_role_only(condition)` — check if condition is exclusively role_check nodes
- `_rule_matches_persona(rule, persona_id)` — check if a PermissionRule applies to a persona
- `_get_permitted_personas(entities, personas, entity_name, operation)` — return persona IDs with a permit rule

These are adapted to take explicit entity/persona lists instead of an AppSpec, since triples are derived before AppSpec construction.

### derive_triples Signature

```python
def derive_triples(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec],
    personas: list[PersonaSpec],
) -> list[VerifiableTriple]:
```

Takes raw lists, not an AppSpec. This is because triple derivation runs in the linker before AppSpec is constructed (step 10b). The function is pure — no side effects, no imports from `dazzle_ui`.

## Integration Points

### Linker (`src/dazzle/core/linker.py`)

New step 10b between scope predicate compilation and AppSpec construction:

```python
# 10. Build FK graph and compile scope predicates
fk_graph = FKGraph.from_entities(list(entities))
entities = _compile_scope_predicates(entities, fk_graph, build_scope_predicate)

# 10b. Derive verifiable triples
from .ir.triples import derive_triples
triples = derive_triples(entities, surfaces, merged_fragment.personas)

# 11. Build final AppSpec
return ir.AppSpec(
    ...
    triples=triples,
)
```

### AppSpec (`src/dazzle/core/ir/appspec.py`)

New field and convenience getters:

```python
from .triples import VerifiableTriple

class AppSpec(BaseModel):
    ...
    triples: list[VerifiableTriple] = Field(default_factory=list)

    def get_triples_for_entity(self, entity: str) -> list[VerifiableTriple]:
        return [t for t in self.triples if t.entity == entity]

    def get_triples_for_persona(self, persona: str) -> list[VerifiableTriple]:
        return [t for t in self.triples if t.persona == persona]

    def get_triple(self, entity: str, surface: str, persona: str) -> VerifiableTriple | None:
        for t in self.triples:
            if t.entity == entity and t.surface == surface and t.persona == persona:
                return t
        return None
```

### Contract Generation (`src/dazzle/testing/ux/contracts.py`)

Rewritten as a thin mapper over `appspec.triples`:

- Each triple with `surface_mode == "list"` → `ListPageContract` (fields from triple)
- Each triple with `surface_mode == "create"` → `CreateFormContract` (required/all from triple)
- Each triple with `surface_mode == "edit"` → `EditFormContract` (editable fields from triple)
- Each triple with `surface_mode == "view"` → `DetailViewContract` (actions from triple)
- Per-persona action presence → `RBACContract` (from triple.actions)
- `WorkspaceContract` stays unchanged (workspaces don't get triples)

The permission helper functions (`_rule_matches_persona`, `_get_permitted_personas`, etc.) are deleted from `contracts.py` — they now live in `triples.py`.

`contracts.py` goes from ~430 lines to ~100 lines.

### No Changes To

- Template compiler (`template_compiler.py`) — continues using its own `_field_type_to_form_type()`
- Page routes (`page_routes.py`) — runtime action gating unchanged
- Form field macro (`form_field.html`) — rendering unchanged
- Workspace renderer — regions unchanged
- Contract checker / HTMX client — consume `Contract` objects as before

## Performance

Measured from example apps:

| App | Entities | Surfaces | Personas | Max Triples | Est. Memory |
|---|---|---|---|---|---|
| simple_task | 8 | 12 | 3 | 36 | ~18 KB |
| fieldtest_hub | 9 | 24 | 4 | 96 | ~48 KB |
| pra | 136 | 65 | 15 | 975 | ~488 KB |

Computation: single pass over entities × surfaces × personas. O(E × S × P) where S is surfaces-per-entity (typically 2-4). Sub-millisecond for small apps, <100ms for PRA.

Memory: <500 KB for the largest app. Adds ~10-15% to AppSpec footprint. Acceptable given AppSpec is already the largest in-memory structure.

## Testing Strategy

New file: `tests/unit/test_triples.py`

### Unit Tests

1. **Widget resolution** — one test per `FieldTypeKind` mapping, plus `_id` suffix convention, plus `source=` override
2. **Action derivation** — test each surface mode produces correct actions; test permission filtering (persona with UPDATE sees `edit_link`, persona without doesn't)
3. **Triple assembly** — small appspec fixture (2 entities, 3 surfaces, 2 personas), assert correct triple count and contents
4. **Framework entity exclusion** — AIJob, FeedbackReport etc. produce no triples
5. **Edge cases** — entity with no surfaces (no triples), surface with no personas (no triples), persona with no permissions (no triple emitted)

### Regression Tests

Run `derive_triples()` on `simple_task` and `fieldtest_hub` appspecs, assert triple counts match expected values.

### Contract Parity Test

For `fieldtest_hub`, verify that the new contracts generated from triples produce identical `contract_id` values as the current `generate_contracts()`. This proves the rewrite is behavior-preserving before deleting the old derivation code.

## Files Changed

| File | Change |
|---|---|
| `src/dazzle/core/ir/triples.py` | **New** — data models, `derive_triples()`, moved permission helpers |
| `src/dazzle/core/ir/__init__.py` | Export new types |
| `src/dazzle/core/ir/appspec.py` | Add `triples` field + 3 convenience getters |
| `src/dazzle/core/linker.py` | Add step 10b calling `derive_triples()` |
| `src/dazzle/testing/ux/contracts.py` | Rewrite as thin mapper over `appspec.triples` |
| `tests/unit/test_triples.py` | **New** — widget, action, assembly, parity tests |
