# Related Display Intent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `related` DSL block to view surfaces that expresses display intent (grouping + display mode) for related entities on detail pages.

**Architecture:** New `RELATED` token in lexer, parser branch in `SurfaceParserMixin`, `RelatedGroup` / `RelatedDisplayMode` IR types on `SurfaceSpec`, link-time validation of entity references and FK paths, `RelatedGroupContext` in template context replacing flat `related_tabs`, template dispatch to mode-specific fragment templates.

**Tech Stack:** Python 3.12+, Pydantic, Jinja2, HTMX, Alpine.js, DaisyUI/Tailwind CSS

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/dazzle/core/lexer.py` | Add `RELATED` token type |
| Modify | `src/dazzle/core/ir/surfaces.py` | Add `RelatedDisplayMode`, `RelatedGroup` types |
| Modify | `src/dazzle/core/ir/__init__.py` | Re-export new types |
| Modify | `src/dazzle/core/dsl_parser_impl/surface.py` | Parse `related` blocks |
| Modify | `src/dazzle/core/linker_impl.py` | Validate related group references |
| Modify | `src/dazzle/core/ir/triples.py` | Add `related_groups` to `VerifiableTriple` |
| Modify | `src/dazzle_ui/runtime/template_context.py` | Add `RelatedGroupContext`, update `DetailContext` |
| Modify | `src/dazzle_ui/converters/template_compiler.py` | Group related tabs into `RelatedGroupContext` |
| Modify | `src/dazzle_ui/templates/components/detail_view.html` | Two-level group/mode dispatch |
| Create | `src/dazzle_ui/templates/fragments/related_table_group.html` | Extracted tab-switching table (existing behavior) |
| Create | `src/dazzle_ui/templates/fragments/related_status_cards.html` | Status card grid fragment |
| Create | `src/dazzle_ui/templates/fragments/related_file_list.html` | File list fragment |
| Modify | `tests/unit/test_parser.py` | Parser + IR type tests for `related` blocks |
| Modify | `tests/unit/test_template_compiler.py` | Linker validation, triple, and template compiler tests |

---

### Task 1: Add `RelatedDisplayMode` and `RelatedGroup` to the IR

**Files:**
- Modify: `src/dazzle/core/ir/surfaces.py:23-30` (add new StrEnum after `BusinessPriority`)
- Modify: `src/dazzle/core/ir/surfaces.py:164-196` (add field to `SurfaceSpec`)
- Modify: `src/dazzle/core/ir/__init__.py:629-640` (re-export new types)

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_parser.py`, add a test that imports the new types:

```python
def test_related_group_ir_types(self):
    """RelatedDisplayMode and RelatedGroup IR types exist."""
    from dazzle.core.ir import RelatedDisplayMode, RelatedGroup

    group = RelatedGroup(
        name="compliance",
        title="Compliance",
        display=RelatedDisplayMode.STATUS_CARDS,
        show=["SelfAssessmentReturn", "VATReturn"],
    )
    assert group.name == "compliance"
    assert group.display == RelatedDisplayMode.STATUS_CARDS
    assert group.show == ["SelfAssessmentReturn", "VATReturn"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_parser.py::TestSurfaceParsing::test_related_group_ir_types -v`
Expected: FAIL with `ImportError: cannot import name 'RelatedDisplayMode'`

- [ ] **Step 3: Add `RelatedDisplayMode` and `RelatedGroup` to `surfaces.py`**

In `src/dazzle/core/ir/surfaces.py`, after the `BusinessPriority` class (line 30), add:

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

In `SurfaceSpec` (around line 192), add after `source`:

```python
    related_groups: list[RelatedGroup] = Field(default_factory=list)
```

- [ ] **Step 4: Re-export from `ir/__init__.py`**

In `src/dazzle/core/ir/__init__.py`, update the surfaces import block (line 629):

```python
# Surfaces
from .surfaces import (
    BusinessPriority,
    Outcome,
    OutcomeKind,
    RelatedDisplayMode,
    RelatedGroup,
    SurfaceAccessSpec,
    SurfaceAction,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
    SurfaceTrigger,
)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_parser.py::TestSurfaceParsing::test_related_group_ir_types -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/surfaces.py src/dazzle/core/ir/__init__.py tests/unit/test_parser.py
git commit -m "feat(ir): add RelatedDisplayMode and RelatedGroup types"
```

---

### Task 2: Add `RELATED` token to the lexer

**Files:**
- Modify: `src/dazzle/core/lexer.py` (add token type)

- [ ] **Step 1: Write the failing test**

```python
def test_lexer_related_token(self):
    """Lexer recognizes 'related' as a keyword token."""
    from dazzle.core.lexer import Lexer, TokenType

    lexer = Lexer("related")
    lexer.tokenize()
    tokens = [t for t in lexer.tokens if t.type != TokenType.EOF and t.type != TokenType.NEWLINE]
    assert len(tokens) == 1
    assert tokens[0].type == TokenType.RELATED
    assert tokens[0].value == "related"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_parser.py::TestSurfaceParsing::test_lexer_related_token -v`
Expected: FAIL with `AttributeError: 'TokenType' object has no attribute 'RELATED'`

- [ ] **Step 3: Add `RELATED` to `TokenType` enum**

In `src/dazzle/core/lexer.py`, add `RELATED = "related"` to the `TokenType` enum. Place it near the other surface-related tokens (after `SECTION = "section"` around line 37):

```python
    SECTION = "section"
    RELATED = "related"
    FIELD = "field"
```

No other changes needed — the `KEYWORDS` set auto-generates from `TokenType`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_parser.py::TestSurfaceParsing::test_lexer_related_token -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/lexer.py tests/unit/test_parser.py
git commit -m "feat(lexer): add RELATED token type"
```

---

### Task 3: Parse `related` blocks in surfaces

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/surface.py:38-164` (add parsing branch and method)
- Test: `tests/unit/test_parser.py`

- [ ] **Step 1: Write the failing test — basic related block**

```python
def test_parse_surface_related_block(self):
    """Surface with a related block parses correctly."""
    dsl = """
module test.core
app test_app "Test App"

entity Contact "Contact":
  id: uuid pk
  first_name: str(100) required

entity TaxReturn "Tax Return":
  id: uuid pk
  contact: ref Contact
  status: str(50)

surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view
  section main:
    field first_name "First Name"
  related compliance "Compliance":
    display: status_cards
    show: TaxReturn
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert len(surface.related_groups) == 1
    group = surface.related_groups[0]
    assert group.name == "compliance"
    assert group.title == "Compliance"
    assert group.display.value == "status_cards"
    assert group.show == ["TaxReturn"]
```

- [ ] **Step 2: Write the failing test — multiple related blocks with multi-entity show**

```python
def test_parse_surface_multiple_related_blocks(self):
    """Surface with multiple related blocks and multi-entity show."""
    dsl = """
module test.core
app test_app "Test App"

entity Contact "Contact":
  id: uuid pk
  name: str(100) required

entity TaxReturn "Tax Return":
  id: uuid pk
  contact: ref Contact

entity Deadline "Deadline":
  id: uuid pk
  contact: ref Contact

entity Document "Document":
  id: uuid pk
  contact: ref Contact

surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view
  section main:
    field name "Name"
  related compliance "Compliance":
    display: status_cards
    show: TaxReturn, Deadline
  related documents "Documents":
    display: file_list
    show: Document
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert len(surface.related_groups) == 2
    assert surface.related_groups[0].name == "compliance"
    assert surface.related_groups[0].show == ["TaxReturn", "Deadline"]
    assert surface.related_groups[1].name == "documents"
    assert surface.related_groups[1].display.value == "file_list"
    assert surface.related_groups[1].show == ["Document"]
```

- [ ] **Step 3: Write the failing test — surface without related blocks has empty list**

```python
def test_parse_surface_no_related_blocks(self):
    """Surface without related blocks has empty related_groups."""
    dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_detail "Task Detail":
  uses entity Task
  mode: view
  section main:
    field title "Title"
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert surface.related_groups == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/unit/test_parser.py -k "test_parse_surface_related" -v`
Expected: 2 FAIL (parsing not implemented), 1 PASS (empty list — already default)

- [ ] **Step 5: Implement `_parse_related_group` and add parser branch**

In `src/dazzle/core/dsl_parser_impl/surface.py`, add `_parse_related_group` method to `SurfaceParserMixin`:

```python
    def _parse_related_group(self) -> ir.RelatedGroup:
        """Parse a related block inside a surface.

        Syntax::

            related name "Title":
              display: table|status_cards|file_list
              show: EntityA, EntityB
        """
        self.advance()  # consume 'related'
        name = self.expect(TokenType.IDENTIFIER).value
        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        display = None
        show: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            if token.value == "display":
                self.advance()
                self.expect(TokenType.COLON)
                mode_token = self.expect_identifier_or_keyword()
                display = ir.RelatedDisplayMode(mode_token.value)
                self.skip_newlines()
            elif token.value == "show":
                self.advance()
                self.expect(TokenType.COLON)
                show.append(self.expect(TokenType.IDENTIFIER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    show.append(self.expect(TokenType.IDENTIFIER).value)
                self.skip_newlines()
            else:
                break

        self.expect(TokenType.DEDENT)

        if display is None:
            self.error("related block requires a 'display:' field")
        if not show:
            self.error("related block requires a 'show:' field with at least one entity")

        return ir.RelatedGroup(
            name=name,
            title=title,
            display=display,
            show=show,
        )
```

In `parse_surface()`, add the `related` branch. In the `while not self.match(TokenType.DEDENT):` loop, after the `elif self.match(TokenType.FOR):` block (around line 125), add:

```python
            # related name "title": (related display group)
            elif self.match(TokenType.RELATED):
                group = self._parse_related_group()
                related_groups.append(group)
```

Also add `related_groups = []` to the locals at the top of `parse_surface()` (after `persona_variants` around line 51), and pass it to the `SurfaceSpec` constructor:

```python
        return ir.SurfaceSpec(
            name=name,
            title=title,
            entity_ref=entity_ref,
            view_ref=view_ref,
            mode=mode,
            priority=priority,
            sections=sections,
            actions=actions,
            ux=ux_spec,
            access=access_spec,
            search_fields=search_fields,
            related_groups=related_groups,
            source=loc,
        )
```

Add to the TYPE_CHECKING block at the top of the class:

```python
        _parse_related_group: Any
```

No — actually `_parse_related_group` is defined on the same class, so no forward declaration needed. But do add `RELATED` to the import or usage: the `TokenType.RELATED` reference works from the existing `from ..lexer import TokenType` import.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_parser.py -k "test_parse_surface_related" -v`
Expected: 3 PASS

- [ ] **Step 7: Run full parser test suite to check for regressions**

Run: `pytest tests/unit/test_parser.py -v --tb=short`
Expected: All existing tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/surface.py tests/unit/test_parser.py
git commit -m "feat(parser): parse related blocks in view surfaces"
```

---

### Task 4: Link-time validation of related groups

**Files:**
- Modify: `src/dazzle/core/linker_impl.py:929-955` (add validation in `validate_references`)
- Test: `tests/unit/test_template_compiler.py` (uses existing `_contact_entity()` fixture)

- [ ] **Step 1: Check how validation is invoked**

Read `src/dazzle/core/linker.py` to see how `validate_references` is called and how errors are surfaced. We need to understand the error path.

- [ ] **Step 2: Write the failing test — unknown entity in show**

```python
def test_related_group_unknown_entity(self):
    """Related group referencing unknown entity produces validation error."""
    from dazzle.core.linker_impl import validate_references, SymbolTable

    surface = ir.SurfaceSpec(
        name="contact_detail",
        title="Contact Detail",
        entity_ref="Contact",
        mode=ir.SurfaceMode.VIEW,
        related_groups=[
            ir.RelatedGroup(
                name="compliance",
                title="Compliance",
                display=ir.RelatedDisplayMode.STATUS_CARDS,
                show=["NonExistentEntity"],
            ),
        ],
    )
    contact = _contact_entity()  # reuse existing fixture from test file
    symbols = SymbolTable()
    symbols.add_entity(contact, "test")
    symbols.add_surface(surface, "test")
    errors = validate_references(symbols)
    assert any("NonExistentEntity" in e and "unknown entity" in e.lower() for e in errors)
```

- [ ] **Step 3: Write the failing test — entity without FK to parent**

```python
def test_related_group_no_fk_to_parent(self):
    """Related group entity without FK to surface entity produces error."""
    from dazzle.core.linker_impl import validate_references, SymbolTable

    # Standalone entity with no FK to Contact
    standalone = ir.EntitySpec(
        name="Standalone",
        title="Standalone",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(name="value", type=ir.FieldType(kind=ir.FieldTypeKind.STRING)),
        ],
    )
    contact = _contact_entity()
    surface = ir.SurfaceSpec(
        name="contact_detail",
        title="Contact Detail",
        entity_ref="Contact",
        mode=ir.SurfaceMode.VIEW,
        related_groups=[
            ir.RelatedGroup(
                name="misc",
                title="Misc",
                display=ir.RelatedDisplayMode.TABLE,
                show=["Standalone"],
            ),
        ],
    )
    symbols = SymbolTable()
    symbols.add_entity(contact, "test")
    symbols.add_entity(standalone, "test")
    symbols.add_surface(surface, "test")
    errors = validate_references(symbols)
    assert any("Standalone" in e and "no FK" in e.lower() for e in errors)
```

- [ ] **Step 4: Write the failing test — duplicate entity across groups**

```python
def test_related_group_duplicate_entity(self):
    """Same entity in two related groups produces validation error."""
    from dazzle.core.linker_impl import validate_references, SymbolTable

    tax_return = ir.EntitySpec(
        name="TaxReturn",
        title="Tax Return",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(
                name="contact",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Contact"),
            ),
        ],
    )
    contact = _contact_entity()
    surface = ir.SurfaceSpec(
        name="contact_detail",
        title="Contact Detail",
        entity_ref="Contact",
        mode=ir.SurfaceMode.VIEW,
        related_groups=[
            ir.RelatedGroup(name="a", title="A", display=ir.RelatedDisplayMode.TABLE, show=["TaxReturn"]),
            ir.RelatedGroup(name="b", title="B", display=ir.RelatedDisplayMode.TABLE, show=["TaxReturn"]),
        ],
    )
    symbols = SymbolTable()
    symbols.add_entity(contact, "test")
    symbols.add_entity(tax_return, "test")
    symbols.add_surface(surface, "test")
    errors = validate_references(symbols)
    assert any("TaxReturn" in e and ("duplicate" in e.lower() or "appears in both" in e.lower()) for e in errors)
```

- [ ] **Step 5: Write the failing test — related block on non-view surface**

```python
def test_related_group_on_non_view_surface(self):
    """Related group on a list surface produces validation error."""
    from dazzle.core.linker_impl import validate_references, SymbolTable

    contact = _contact_entity()
    surface = ir.SurfaceSpec(
        name="contact_list",
        title="Contacts",
        entity_ref="Contact",
        mode=ir.SurfaceMode.LIST,
        related_groups=[
            ir.RelatedGroup(name="a", title="A", display=ir.RelatedDisplayMode.TABLE, show=["TaxReturn"]),
        ],
    )
    symbols = SymbolTable()
    symbols.add_entity(contact, "test")
    symbols.add_surface(surface, "test")
    errors = validate_references(symbols)
    assert any("related" in e.lower() and "view" in e.lower() for e in errors)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/unit/test_template_compiler.py -k "test_related_group_unknown or test_related_group_no_fk or test_related_group_duplicate or test_related_group_on_non" -v`
Expected: 4 FAIL

- [ ] **Step 7: Implement validation in `validate_references`**

In `src/dazzle/core/linker_impl.py`, inside `validate_references()`, after the existing surface validation block (after the action outcome checks, around line 980), add:

```python
        # Validate related groups (display intent)
        if surface.related_groups:
            if surface.mode != ir.SurfaceMode.VIEW:
                errors.append(
                    f"Surface '{surface_name}' has related blocks but is not mode: view "
                    f"(related blocks are only valid on view surfaces)"
                )

            seen_entities: set[str] = set()
            for group in surface.related_groups:
                for entity_in_show in group.show:
                    # Check entity exists
                    if entity_in_show not in symbols.entities:
                        errors.append(
                            f"Surface '{surface_name}' related group '{group.name}' "
                            f"references unknown entity '{entity_in_show}'"
                        )
                        continue

                    # Check duplicate across groups
                    if entity_in_show in seen_entities:
                        errors.append(
                            f"Surface '{surface_name}': entity '{entity_in_show}' "
                            f"appears in both related group '{group.name}' and a "
                            f"previous group (duplicate)"
                        )
                    seen_entities.add(entity_in_show)

                    # Check FK back to parent entity
                    if surface.entity_ref:
                        ref_entity = symbols.entities[entity_in_show]
                        has_fk = False
                        for f in ref_entity.fields:
                            if (
                                f.type.kind == ir.FieldTypeKind.REF
                                and f.type.ref_entity == surface.entity_ref
                            ):
                                has_fk = True
                                break
                        if not has_fk:
                            errors.append(
                                f"Surface '{surface_name}' related group '{group.name}': "
                                f"entity '{entity_in_show}' has no FK to "
                                f"'{surface.entity_ref}'"
                            )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/unit/test_template_compiler.py -k "test_related_group_unknown or test_related_group_no_fk or test_related_group_duplicate or test_related_group_on_non" -v`
Expected: 4 PASS

- [ ] **Step 9: Commit**

```bash
git add src/dazzle/core/linker_impl.py tests/unit/test_template_compiler.py
git commit -m "feat(linker): validate related group entity refs and FK paths"
```

---

### Task 5: Add `related_groups` to `VerifiableTriple`

**Files:**
- Modify: `src/dazzle/core/ir/triples.py:432-459` (`VerifiableTriple` class)
- Modify: `src/dazzle/core/ir/triples.py:541-601` (`derive_triples` function)

- [ ] **Step 1: Write the failing test**

```python
def test_triple_includes_related_groups(self):
    """VerifiableTriple includes related_groups from surface."""
    from dazzle.core.ir.triples import derive_triples

    contact = _contact_entity()
    tax_return = ir.EntitySpec(
        name="TaxReturn",
        title="Tax Return",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(
                name="contact",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Contact"),
            ),
        ],
    )
    surface = ir.SurfaceSpec(
        name="contact_detail",
        title="Contact Detail",
        entity_ref="Contact",
        mode=ir.SurfaceMode.VIEW,
        sections=[
            ir.SurfaceSection(name="main", elements=[
                ir.SurfaceElement(field_name="full_name"),
            ]),
        ],
        related_groups=[
            ir.RelatedGroup(
                name="compliance",
                title="Compliance",
                display=ir.RelatedDisplayMode.STATUS_CARDS,
                show=["TaxReturn"],
            ),
        ],
    )
    persona = ir.PersonaSpec(id="admin", name="Admin", role="admin")

    triples = derive_triples([contact, tax_return], [surface], [persona])
    # Find the triple for Contact/contact_detail
    triple = next(t for t in triples if t.surface == "contact_detail")
    assert triple.related_groups == ["compliance"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_template_compiler.py -k "test_triple_includes_related_groups" -v`
Expected: FAIL — `VerifiableTriple` has no `related_groups` field

- [ ] **Step 3: Add `related_groups` field to `VerifiableTriple`**

In `src/dazzle/core/ir/triples.py`, add to `VerifiableTriple` (after `fields` at line 458):

```python
    related_groups: list[str] = Field(default_factory=list)
```

Add the `Field` import at the top if not already present:

```python
from pydantic import BaseModel, ConfigDict, Field
```

- [ ] **Step 4: Populate `related_groups` in `derive_triples`**

In `derive_triples()`, inside the loop where `VerifiableTriple` is constructed (around line 590), extract group names from the surface:

```python
                # Extract related group names from surface
                surface_related_groups = [
                    g.name for g in getattr(surface, "related_groups", [])
                ]

                triples.append(
                    VerifiableTriple(
                        entity=entity_name,
                        surface=surface_name,
                        persona=persona_id,
                        surface_mode=surface_mode,
                        actions=persona_actions,
                        fields=fields,
                        related_groups=surface_related_groups,
                    )
                )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_template_compiler.py -k "test_triple_includes_related_groups" -v`
Expected: PASS

- [ ] **Step 6: Run full triple test suite**

Run: `pytest tests/unit/ -k "triple" -v --tb=short`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/ir/triples.py tests/unit/test_template_compiler.py
git commit -m "feat(triples): add related_groups to VerifiableTriple"
```

---

### Task 6: Add `RelatedGroupContext` and update `DetailContext`

**Files:**
- Modify: `src/dazzle_ui/runtime/template_context.py:142-196` (add new model, update `DetailContext`)

- [ ] **Step 1: Write the failing test**

```python
def test_related_group_context_model(self):
    """RelatedGroupContext wraps RelatedTabContext with display mode."""
    from dazzle_ui.runtime.template_context import RelatedGroupContext, RelatedTabContext

    tab = RelatedTabContext(
        tab_id="tab-tax-return",
        label="Tax Return",
        entity_name="TaxReturn",
        api_endpoint="/tax-returns",
        filter_field="contact",
        columns=[],
    )
    group = RelatedGroupContext(
        group_id="group-compliance",
        label="Compliance",
        display="status_cards",
        tabs=[tab],
    )
    assert group.display == "status_cards"
    assert len(group.tabs) == 1
    assert group.is_auto is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_template_compiler.py -k "test_related_group_context_model" -v`
Expected: FAIL with `ImportError: cannot import name 'RelatedGroupContext'`

- [ ] **Step 3: Add `RelatedGroupContext` to `template_context.py`**

In `src/dazzle_ui/runtime/template_context.py`, after `RelatedTabContext` (around line 161), add:

```python
class RelatedGroupContext(BaseModel):
    """A group of related entity tabs with a shared display mode."""

    group_id: str  # DOM id (e.g. "group-compliance")
    label: str  # Display label (e.g. "Compliance")
    display: str  # "table", "status_cards", "file_list"
    tabs: list[RelatedTabContext]  # Individual entities in this group
    is_auto: bool = False  # True for the auto-generated "Other" group
```

- [ ] **Step 4: Update `DetailContext` to use `related_groups`**

In `DetailContext`, replace:

```python
    related_tabs: list[RelatedTabContext] = Field(default_factory=list)
```

with:

```python
    related_groups: list[RelatedGroupContext] = Field(default_factory=list)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_template_compiler.py -k "test_related_group_context_model" -v`
Expected: PASS

- [ ] **Step 6: Commit (tests will be broken — template compiler and existing tests still use `related_tabs`)**

```bash
git add src/dazzle_ui/runtime/template_context.py tests/unit/test_template_compiler.py
git commit -m "feat(context): add RelatedGroupContext, update DetailContext"
```

---

### Task 7: Update template compiler to produce `RelatedGroupContext`

**Files:**
- Modify: `src/dazzle_ui/converters/template_compiler.py:18-33` (imports)
- Modify: `src/dazzle_ui/converters/template_compiler.py:778-865` (grouping logic)
- Modify: `tests/unit/test_template_compiler.py` (update existing tests)

- [ ] **Step 1: Write the failing test — surface with related groups**

```python
def test_view_surface_with_related_groups(self):
    """VIEW surface with related_groups produces RelatedGroupContext."""
    company = _company_entity()
    contact = _contact_entity()
    task = _task_entity()
    appspec = ir.AppSpec(
        name="test_app",
        title="Test App",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[company, contact, task]),
        surfaces=[
            ir.SurfaceSpec(
                name="company_detail",
                title="Company Detail",
                entity_ref="Company",
                mode=SurfaceMode.VIEW,
                related_groups=[
                    ir.RelatedGroup(
                        name="people",
                        title="People",
                        display=ir.RelatedDisplayMode.STATUS_CARDS,
                        show=["Contact"],
                    ),
                ],
            ),
        ],
    )
    contexts = compile_appspec_to_templates(appspec)
    detail_ctx = contexts["/company/{id}"]
    assert len(detail_ctx.detail.related_groups) == 2  # 1 declared + 1 auto ("Other" with Task)
    people_group = detail_ctx.detail.related_groups[0]
    assert people_group.label == "People"
    assert people_group.display == "status_cards"
    assert people_group.is_auto is False
    assert len(people_group.tabs) == 1
    assert people_group.tabs[0].entity_name == "Contact"
    # Auto "Other" group for Task (not in any related group)
    other_group = detail_ctx.detail.related_groups[1]
    assert other_group.display == "table"
    assert other_group.is_auto is True
    assert len(other_group.tabs) == 1
    assert other_group.tabs[0].entity_name == "Task"
```

- [ ] **Step 2: Write the failing test — surface without related groups auto-groups all**

```python
def test_view_surface_without_related_groups_auto_groups(self):
    """VIEW surface without related_groups auto-groups all tabs."""
    appspec = self._make_hub_appspec()
    contexts = compile_appspec_to_templates(appspec)
    detail_ctx = contexts["/company/{id}"]
    assert len(detail_ctx.detail.related_groups) == 1
    auto_group = detail_ctx.detail.related_groups[0]
    assert auto_group.is_auto is True
    assert auto_group.display == "table"
    assert len(auto_group.tabs) == 2  # Contact + Task
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_template_compiler.py -k "test_view_surface_with_related_groups or test_view_surface_without_related_groups_auto" -v`
Expected: FAIL

- [ ] **Step 4: Update template compiler imports**

In `src/dazzle_ui/converters/template_compiler.py`, update the import block (line 18):

```python
from dazzle_ui.runtime.template_context import (
    ColumnContext,
    DetailContext,
    ExternalLinkAction,
    FieldContext,
    FieldSourceContext,
    FormContext,
    FormSectionContext,
    NavItemContext,
    PageContext,
    RelatedGroupContext,
    RelatedTabContext,
    ReviewActionContext,
    ReviewContext,
    TableContext,
    TransitionContext,
)
```

- [ ] **Step 5: Add grouping logic in `_compile_view_surface`**

After the existing related tab building code (after the `poly_refs` loop, around line 833), replace the `related_tabs=related_tabs` assignment in the `DetailContext` constructor with grouping logic:

```python
    # Group related tabs by surface-declared related groups
    related_groups: list[RelatedGroupContext] = []
    if surface.related_groups:
        claimed: set[str] = set()
        for group in surface.related_groups:
            group_tabs = [t for t in related_tabs if t.entity_name in group.show]
            claimed.update(group.show)
            if group_tabs:
                related_groups.append(
                    RelatedGroupContext(
                        group_id=f"group-{group.name}",
                        label=group.title or group.name.replace("_", " ").title(),
                        display=group.display.value,
                        tabs=group_tabs,
                    )
                )
        # Auto-group unclaimed tabs into "Other"
        unclaimed = [t for t in related_tabs if t.entity_name not in claimed]
        if unclaimed:
            related_groups.append(
                RelatedGroupContext(
                    group_id="group-other",
                    label="Other",
                    display="table",
                    tabs=unclaimed,
                    is_auto=True,
                )
            )
    elif related_tabs:
        # No related groups declared — auto-group everything
        related_groups.append(
            RelatedGroupContext(
                group_id="group-auto",
                label="Related",
                display="table",
                tabs=related_tabs,
                is_auto=True,
            )
        )
```

Then in the `DetailContext` constructor, replace `related_tabs=related_tabs` with `related_groups=related_groups`.

- [ ] **Step 6: Update all existing tests that reference `detail.related_tabs`**

Every test that accesses `detail.related_tabs` needs to go through `related_groups`. The pattern is:

- `detail.related_tabs` → `detail.related_groups[0].tabs` (for auto-grouped surfaces)
- `len(detail.related_tabs)` → `len(detail.related_groups[0].tabs)` (counting tabs within auto group)
- For tests checking "no related tabs", check `len(detail.related_groups) == 0`

Update each test in `test_template_compiler.py` that references `.related_tabs`. Key tests to update:

- `test_view_surface_has_related_tabs`: `len(detail.related_groups) == 1` and `len(detail.related_groups[0].tabs) == 2`
- `test_related_tab_labels`: `tabs = contexts["/company/{id}"].detail.related_groups[0].tabs`
- `test_related_tab_filter_field`: same pattern
- `test_related_tab_api_endpoint`: same pattern
- `test_related_tab_columns_exclude_fk`: same pattern
- `test_related_tab_create_url`: same pattern
- `test_related_tab_detail_url`: same pattern
- `test_list_surface_has_no_related_tabs`: `len(detail.related_groups) == 0`
- All polymorphic FK tests: same `.related_groups[0].tabs` pattern
- Any test checking `detail.related_tabs` count of 0: `len(detail.related_groups) == 0`

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/unit/test_template_compiler.py -v --tb=short`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/dazzle_ui/converters/template_compiler.py tests/unit/test_template_compiler.py
git commit -m "feat(compiler): group related tabs into RelatedGroupContext"
```

---

### Task 8: Extract table group fragment template

**Files:**
- Create: `src/dazzle_ui/templates/fragments/related_table_group.html`
- Modify: `src/dazzle_ui/templates/components/detail_view.html`

- [ ] **Step 1: Create `related_table_group.html`**

Extract the existing tab-switching code from `detail_view.html` into a fragment. This template receives a `group` variable with `.tabs`:

```html
{# Table group — Alpine tab switching within a related group #}
{% set first_tab_id = group.tabs[0].tab_id if group.tabs else '' %}
<div x-data="{ activeTab: '{{ first_tab_id }}' }">
  {% if group.tabs | length > 1 %}
  <div class="tabs tabs-bordered" role="tablist">
    {% for tab in group.tabs %}
    {% if tab.visible | default(true) %}
    <button class="tab"
            :class="activeTab === '{{ tab.tab_id }}' && 'tab-active'"
            role="tab"
            :aria-selected="activeTab === '{{ tab.tab_id }}'"
            @click="activeTab = '{{ tab.tab_id }}'">
      {{ tab.label }}
      <span class="badge badge-sm ml-1">{{ tab.total }}</span>
    </button>
    {% endif %}
    {% endfor %}
  </div>
  {% endif %}

  {% for tab in group.tabs %}
  {% if tab.visible | default(true) %}
  <div {% if group.tabs | length > 1 %}x-show="activeTab === '{{ tab.tab_id }}'"{% endif %} role="tabpanel">
    <div class="card bg-base-100 shadow-sm mt-2">
      <div class="card-body p-0">
        {% if tab.create_url %}
        <div class="flex justify-end p-3 pb-0">
          <a href="{{ tab.create_url }}?{{ tab.filter_field }}={{ detail.item.get('id', '') }}{% if tab.filter_type_field %}&amp;{{ tab.filter_type_field }}={{ tab.filter_type_value }}{% endif %}"
             class="btn btn-primary btn-sm"
             data-dazzle-action="{{ tab.entity_name }}.create">
            + New {{ tab.label }}
          </a>
        </div>
        {% endif %}

        <div class="overflow-x-auto">
          <table class="table table-zebra w-full" data-entity="{{ tab.entity_name }}">
            <thead>
              <tr>
                {% for col in tab.columns %}
                <th scope="col">{{ col.label }}</th>
                {% endfor %}
              </tr>
            </thead>
            <tbody>
              {% if tab.rows %}
              {% for item in tab.rows %}
              <tr class="hover cursor-pointer"
                  {% if tab.detail_url_template %}
                  hx-get="{{ tab.detail_url_template.replace('{id}', item.id | string) }}"
                  hx-push-url="true"
                  hx-target="body"
                  hx-swap="innerHTML"
                  {% endif %}>
                {% for col in tab.columns %}
                <td>
                  {% if col.type == "badge" %}
                    <span class="badge {{ item[col.key] | badge_class }}">{{ item[col.key] | default("") }}</span>
                  {% elif col.type == "bool" %}
                    {{ item[col.key] | bool_icon }}
                  {% elif col.type == "date" %}
                    {{ item[col.key] | dateformat }}
                  {% elif col.type == "currency" %}
                    {{ item[col.key] | currency(col.currency_code or "GBP") }}
                  {% else %}
                    {{ item[col.key] | default("") | truncate_text }}
                  {% endif %}
                </td>
                {% endfor %}
              </tr>
              {% endfor %}
              {% else %}
              <tr>
                <td colspan="{{ tab.columns | length }}" class="text-center py-8 text-base-content/50">
                  No {{ tab.label | lower }} found.
                </td>
              </tr>
              {% endif %}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
  {% endif %}
  {% endfor %}
</div>
```

- [ ] **Step 2: Create `related_status_cards.html`**

```html
{# Status cards — grid of cards with status badge for each related entity #}
{% for tab in group.tabs %}
{% if tab.visible | default(true) %}
<div class="mb-4">
  {% if group.tabs | length > 1 %}
  <h4 class="text-sm font-medium text-base-content/70 mb-2">{{ tab.label }}</h4>
  {% endif %}

  {% if tab.create_url %}
  <div class="flex justify-end mb-2">
    <a href="{{ tab.create_url }}?{{ tab.filter_field }}={{ detail.item.get('id', '') }}"
       class="btn btn-primary btn-sm"
       data-dazzle-action="{{ tab.entity_name }}.create">
      + New {{ tab.label }}
    </a>
  </div>
  {% endif %}

  {% if tab.rows %}
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
    {% for item in tab.rows %}
    <div class="card bg-base-100 shadow-sm border border-base-200 hover:shadow-md transition-shadow cursor-pointer"
         {% if tab.detail_url_template %}
         hx-get="{{ tab.detail_url_template.replace('{id}', item.id | string) }}"
         hx-push-url="true"
         hx-target="body"
         hx-swap="innerHTML"
         {% endif %}>
      <div class="card-body p-4">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            {% for col in tab.columns[:3] %}
            {% if loop.first %}
            <p class="font-medium truncate">{{ item[col.key] | default("—") }}</p>
            {% else %}
            <p class="text-sm text-base-content/60 truncate">{{ item[col.key] | default("—") }}</p>
            {% endif %}
            {% endfor %}
          </div>
          {% for col in tab.columns if col.type == "badge" %}
          {% if loop.first %}
          <span class="badge badge-sm {{ item[col.key] | badge_class }} shrink-0">{{ item[col.key] | default("") }}</span>
          {% endif %}
          {% endfor %}
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <p class="text-center py-6 text-base-content/50">No {{ tab.label | lower }} found.</p>
  {% endif %}
</div>
{% endif %}
{% endfor %}
```

- [ ] **Step 3: Create `related_file_list.html`**

```html
{# File list — compact rows for document/evidence entities #}
{% for tab in group.tabs %}
{% if tab.visible | default(true) %}
<div class="mb-4">
  {% if group.tabs | length > 1 %}
  <h4 class="text-sm font-medium text-base-content/70 mb-2">{{ tab.label }}</h4>
  {% endif %}

  {% if tab.create_url %}
  <div class="flex justify-end mb-2">
    <a href="{{ tab.create_url }}?{{ tab.filter_field }}={{ detail.item.get('id', '') }}"
       class="btn btn-primary btn-sm"
       data-dazzle-action="{{ tab.entity_name }}.create">
      + New {{ tab.label }}
    </a>
  </div>
  {% endif %}

  {% if tab.rows %}
  <div class="divide-y divide-base-200 border border-base-200 rounded-lg bg-base-100">
    {% for item in tab.rows %}
    <div class="flex items-center gap-3 px-4 py-3 hover:bg-base-200/50 cursor-pointer"
         {% if tab.detail_url_template %}
         hx-get="{{ tab.detail_url_template.replace('{id}', item.id | string) }}"
         hx-push-url="true"
         hx-target="body"
         hx-swap="innerHTML"
         {% endif %}>
      <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-base-content/40 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
      <div class="min-w-0 flex-1">
        {% for col in tab.columns[:2] %}
        {% if loop.first %}
        <p class="text-sm font-medium truncate">{{ item[col.key] | default("—") }}</p>
        {% else %}
        <p class="text-xs text-base-content/50">{{ item[col.key] | default("") }}</p>
        {% endif %}
        {% endfor %}
      </div>
      {% for col in tab.columns if col.type == "date" %}
      {% if loop.first %}
      <span class="text-xs text-base-content/50 shrink-0">{{ item[col.key] | dateformat }}</span>
      {% endif %}
      {% endfor %}
    </div>
    {% endfor %}
  </div>
  {% else %}
  <p class="text-center py-6 text-base-content/50">No {{ tab.label | lower }} found.</p>
  {% endif %}
</div>
{% endif %}
{% endfor %}
```

- [ ] **Step 4: Update `detail_view.html` to use group dispatch**

Replace the entire `{% if detail.related_tabs %}` block (lines 128-218) with:

```html
  {# Related entity groups (#related-display-intent) #}
  {% if detail.related_groups %}
  {% block detail_related_groups %}
  {% for group in detail.related_groups %}
  <div class="mt-6" data-dazzle-related-group="{{ group.group_id }}">
    {% if detail.related_groups | length > 1 or not group.is_auto %}
    <h3 class="text-lg font-semibold mb-3">{{ group.label }}</h3>
    {% endif %}

    {% if group.display == "status_cards" %}
      {% include "fragments/related_status_cards.html" %}
    {% elif group.display == "file_list" %}
      {% include "fragments/related_file_list.html" %}
    {% else %}
      {% include "fragments/related_table_group.html" %}
    {% endif %}
  </div>
  {% endfor %}
  {% endblock detail_related_groups %}
  {% endif %}
```

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/unit/test_template_compiler.py tests/unit/test_template_rendering.py -v --tb=short`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_ui/templates/components/detail_view.html \
        src/dazzle_ui/templates/fragments/related_table_group.html \
        src/dazzle_ui/templates/fragments/related_status_cards.html \
        src/dazzle_ui/templates/fragments/related_file_list.html
git commit -m "feat(templates): group dispatch for related display modes"
```

---

### Task 9: Full integration test and regression sweep

**Files:**
- No new files — run existing test suites

- [ ] **Step 1: Run parser tests**

Run: `pytest tests/unit/test_parser.py -v --tb=short`
Expected: All PASS

- [ ] **Step 2: Run template compiler tests**

Run: `pytest tests/unit/test_template_compiler.py -v --tb=short`
Expected: All PASS

- [ ] **Step 3: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" --tb=short -q`
Expected: All PASS (no regressions)

- [ ] **Step 4: Run linting**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean

- [ ] **Step 5: Run type checking**

Run: `mypy src/dazzle`
Expected: Clean (or no new errors)

- [ ] **Step 6: Commit any lint/format fixes**

```bash
git add -u
git commit -m "style: lint and format fixes for related display intent"
```

---

### Task 10: Update investigation notes and memory

**Files:**
- Modify: `dev_docs/related-display-intent-notes.md` (mark as implemented)

- [ ] **Step 1: Update investigation notes status**

Change the status line at the top to `Implemented` and add a summary of what was built.

- [ ] **Step 2: Commit**

```bash
git add dev_docs/related-display-intent-notes.md
git commit -m "docs: mark related display intent as implemented"
```
