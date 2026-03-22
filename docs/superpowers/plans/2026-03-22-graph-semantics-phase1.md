# Graph Semantics Phase 1 — Parser + IR + Validator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entities can declare `graph_edge:` and `graph_node:` blocks; `dazzle validate` checks correctness; `dazzle lint` suggests graph patterns.

**Architecture:** Two new Pydantic IR types (`GraphEdgeSpec`, `GraphNodeSpec`) attached as optional fields on `EntitySpec`. Parser recognizes new indented blocks inside entity declarations. Validator checks field references, types, and cross-entity consistency. Extended lint suggests graph patterns for entities that look like edges.

**Tech Stack:** Python 3.12, Pydantic v2, existing parser mixin pattern, existing validator/lint infrastructure.

**Spec:** `docs/superpowers/specs/2026-03-22-graph-semantics-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/core/ir/domain.py` | Modify | Add `GraphEdgeSpec`, `GraphNodeSpec` classes; add fields to `EntitySpec` |
| `src/dazzle/core/ir/__init__.py` | Modify | Re-export new types |
| `src/dazzle/core/lexer.py` | Modify | Add 5 new keyword tokens |
| `src/dazzle/core/dsl_parser_impl/entity.py` | Modify | Parse `graph_edge:` and `graph_node:` blocks |
| `src/dazzle/core/validator.py` | Modify | Add `validate_graph_declarations()` |
| `src/dazzle/core/lint.py` | Modify | Wire graph validation into `lint_appspec()` |
| `tests/unit/test_graph_semantics.py` | Create | All tests for graph parsing, validation, and lint hints |

---

### Task 1: IR Types

**Files:**
- Modify: `src/dazzle/core/ir/domain.py` (add classes before `EntitySpec`, add fields to `EntitySpec`)
- Modify: `src/dazzle/core/ir/__init__.py` (re-export new types)
- Test: `tests/unit/test_graph_semantics.py`

- [ ] **Step 1: Write failing test for IR types**

Create `tests/unit/test_graph_semantics.py`:

```python
"""Tests for graph_edge: and graph_node: DSL constructs (Phase 1 — #619)."""

from dazzle.core import ir


class TestGraphIRTypes:
    """GraphEdgeSpec and GraphNodeSpec construction."""

    def test_graph_edge_spec_defaults(self) -> None:
        spec = ir.GraphEdgeSpec(source="source_node", target="target_node")
        assert spec.source == "source_node"
        assert spec.target == "target_node"
        assert spec.type_field is None
        assert spec.weight_field is None
        assert spec.directed is True
        assert spec.acyclic is False

    def test_graph_edge_spec_full(self) -> None:
        spec = ir.GraphEdgeSpec(
            source="src",
            target="tgt",
            type_field="relationship",
            weight_field="importance",
            directed=False,
            acyclic=True,
        )
        assert spec.type_field == "relationship"
        assert spec.weight_field == "importance"
        assert spec.directed is False
        assert spec.acyclic is True

    def test_graph_edge_spec_frozen(self) -> None:
        spec = ir.GraphEdgeSpec(source="a", target="b")
        try:
            spec.source = "c"  # type: ignore[misc]
            assert False, "should be frozen"
        except Exception:
            pass

    def test_graph_node_spec(self) -> None:
        spec = ir.GraphNodeSpec(edge_entity="NodeEdge", display="title")
        assert spec.edge_entity == "NodeEdge"
        assert spec.display == "title"

    def test_graph_node_spec_display_optional(self) -> None:
        spec = ir.GraphNodeSpec(edge_entity="NodeEdge")
        assert spec.display is None

    def test_entity_spec_graph_fields_default_none(self) -> None:
        entity = ir.EntitySpec(
            name="Foo",
            fields=[ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))],
        )
        assert entity.graph_edge is None
        assert entity.graph_node is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphIRTypes -v`
Expected: FAIL — `ir.GraphEdgeSpec` does not exist.

- [ ] **Step 3: Add IR types to domain.py**

In `src/dazzle/core/ir/domain.py`, add before the `EntitySpec` class:

```python
class GraphEdgeSpec(BaseModel):
    """Formal graph edge declaration on an entity.

    Declares that this entity represents edges in a property graph.
    source and target must name ref fields on the same entity.
    """

    source: str
    target: str
    type_field: str | None = None
    weight_field: str | None = None
    directed: bool = True
    acyclic: bool = False

    model_config = ConfigDict(frozen=True)


class GraphNodeSpec(BaseModel):
    """Optional graph node annotation on an entity.

    Declares that this entity represents nodes connected by a specific
    edge entity.
    """

    edge_entity: str
    display: str | None = None

    model_config = ConfigDict(frozen=True)
```

Add two fields to `EntitySpec` (after `display_field`, before `source`):

```python
    # v0.46.0: Graph semantics (#619)
    graph_edge: GraphEdgeSpec | None = None
    graph_node: GraphNodeSpec | None = None
```

- [ ] **Step 4: Re-export from ir/__init__.py**

In `src/dazzle/core/ir/__init__.py`, add to the `from .domain import` block:

```python
    GraphEdgeSpec,
    GraphNodeSpec,
```

And add to `__all__`:

```python
    "GraphEdgeSpec",
    "GraphNodeSpec",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphIRTypes -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/domain.py src/dazzle/core/ir/__init__.py tests/unit/test_graph_semantics.py
git commit -m "feat(ir): add GraphEdgeSpec and GraphNodeSpec types (#619)"
```

---

### Task 2: Lexer Tokens

**Files:**
- Modify: `src/dazzle/core/lexer.py` (add 5 tokens to `TokenType` enum)

- [ ] **Step 1: Add tokens to lexer**

In `src/dazzle/core/lexer.py`, add a new section after the `# v0.44.0 Runtime Parameters` block (before the comparison operators section):

```python
    # v0.46.0 Graph Semantics Keywords (#619)
    GRAPH_EDGE = "graph_edge"
    GRAPH_NODE = "graph_node"
    TARGET = "target"
    WEIGHT = "weight"
    DIRECTED = "directed"
    ACYCLIC = "acyclic"
    EDGES = "edges"
```

Note: `SOURCE` and `DISPLAY` already exist as tokens. `TRUE`/`FALSE` already exist for the boolean values of `directed` and `acyclic`.

- [ ] **Step 2: Verify no regressions**

Run: `pytest tests/unit/test_parser.py -x -q`
Expected: All existing tests pass (111 tests).

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/core/lexer.py
git commit -m "feat(lexer): add graph_edge/graph_node keyword tokens (#619)"
```

---

### Task 3: Parser — `graph_edge:` Block

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py` (add parsing logic)
- Test: `tests/unit/test_graph_semantics.py`

- [ ] **Step 1: Write failing test for graph_edge parsing**

Append to `tests/unit/test_graph_semantics.py`:

```python
from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl


def _parse(dsl: str) -> ir.AppSpec:
    """Parse DSL text and link into an AppSpec."""
    from dazzle.core.linker import link_modules

    mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(
        dsl, Path("test.dsl")
    )
    return link_modules(mod_name, app_name, app_title, app_config, uses, [fragment])


class TestGraphEdgeParsing:
    """Parser recognizes graph_edge: blocks."""

    def test_basic_graph_edge(self) -> None:
        dsl = '''
module test
app g "G"

entity Node "Node":
  id: uuid pk
  title: str(200) required

entity NodeEdge "Edge":
  id: uuid pk
  source_node: ref Node required
  target_node: ref Node required
  relationship: enum[sequel,fork,reference]
  weight: int optional

  graph_edge:
    source: source_node
    target: target_node
    type: relationship
    weight: weight
'''
        appspec = _parse(dsl)
        edge_entity = next(e for e in appspec.domain.entities if e.name == "NodeEdge")
        ge = edge_entity.graph_edge
        assert ge is not None
        assert ge.source == "source_node"
        assert ge.target == "target_node"
        assert ge.type_field == "relationship"
        assert ge.weight_field == "weight"
        assert ge.directed is True
        assert ge.acyclic is False

    def test_graph_edge_with_booleans(self) -> None:
        dsl = '''
module test
app g "G"

entity Node "Node":
  id: uuid pk

entity Edge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
    directed: false
    acyclic: true
'''
        appspec = _parse(dsl)
        edge_entity = next(e for e in appspec.domain.entities if e.name == "Edge")
        ge = edge_entity.graph_edge
        assert ge is not None
        assert ge.directed is False
        assert ge.acyclic is True

    def test_graph_edge_minimal(self) -> None:
        dsl = '''
module test
app g "G"

entity Node "Node":
  id: uuid pk

entity Edge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
'''
        appspec = _parse(dsl)
        edge_entity = next(e for e in appspec.domain.entities if e.name == "Edge")
        ge = edge_entity.graph_edge
        assert ge is not None
        assert ge.source == "src"
        assert ge.target == "tgt"
        assert ge.type_field is None
        assert ge.weight_field is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphEdgeParsing -v`
Expected: FAIL — parser doesn't recognize `graph_edge:`.

- [ ] **Step 3: Implement graph_edge parsing in entity.py**

In `src/dazzle/core/dsl_parser_impl/entity.py`:

1. Add a `graph_edge` variable at the top of `parse_entity()`, near the other optional vars:

```python
        # v0.46.0: Graph semantics (#619)
        graph_edge: ir.GraphEdgeSpec | None = None
        graph_node: ir.GraphNodeSpec | None = None
```

2. Add parsing block in the `while not self.match(TokenType.DEDENT):` loop, after the `bulk:` block (before the `transitions:` block):

```python
            # v0.46.0: Check for graph_edge: block (#619)
            if self.match(TokenType.GRAPH_EDGE):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                ge_source: str | None = None
                ge_target: str | None = None
                ge_type: str | None = None
                ge_weight: str | None = None
                ge_directed: bool = True
                ge_acyclic: bool = False

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    if self.match(TokenType.SOURCE):
                        self.advance()
                        self.expect(TokenType.COLON)
                        ge_source = self.expect_identifier_or_keyword().value
                    elif self.match(TokenType.TARGET):
                        self.advance()
                        self.expect(TokenType.COLON)
                        ge_target = self.expect_identifier_or_keyword().value
                    elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "type":
                        self.advance()
                        self.expect(TokenType.COLON)
                        ge_type = self.expect_identifier_or_keyword().value
                    elif self.match(TokenType.WEIGHT):
                        self.advance()
                        self.expect(TokenType.COLON)
                        ge_weight = self.expect_identifier_or_keyword().value
                    elif self.match(TokenType.DIRECTED):
                        self.advance()
                        self.expect(TokenType.COLON)
                        if self.match(TokenType.TRUE):
                            self.advance()
                            ge_directed = True
                        elif self.match(TokenType.FALSE):
                            self.advance()
                            ge_directed = False
                        else:
                            raise make_parse_error(
                                "Expected true or false for directed",
                                self.file,
                                self.current_token().line,
                            )
                    elif self.match(TokenType.ACYCLIC):
                        self.advance()
                        self.expect(TokenType.COLON)
                        if self.match(TokenType.TRUE):
                            self.advance()
                            ge_acyclic = True
                        elif self.match(TokenType.FALSE):
                            self.advance()
                            ge_acyclic = False
                        else:
                            raise make_parse_error(
                                "Expected true or false for acyclic",
                                self.file,
                                self.current_token().line,
                            )
                    else:
                        raise make_parse_error(
                            f"Unexpected token in graph_edge: block: {self.current_token().value}",
                            self.file,
                            self.current_token().line,
                        )
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

                if ge_source is None or ge_target is None:
                    raise make_parse_error(
                        "graph_edge: requires both source and target fields",
                        self.file,
                        self.current_token().line,
                    )

                graph_edge = ir.GraphEdgeSpec(
                    source=ge_source,
                    target=ge_target,
                    type_field=ge_type,
                    weight_field=ge_weight,
                    directed=ge_directed,
                    acyclic=ge_acyclic,
                )
                self.skip_newlines()
                continue
```

3. Pass `graph_edge` and `graph_node` to the `EntitySpec` constructor at the end of `parse_entity()`:

```python
        return ir.EntitySpec(
            ...
            display_field=display_field,
            graph_edge=graph_edge,
            graph_node=graph_node,
            source=loc,
        )
```

**Important:** `type` is a Python built-in but in the DSL it's just an identifier — the lexer won't produce a `TYPE` token. It will produce `IDENTIFIER("type")`. So we check `self.match(TokenType.IDENTIFIER) and self.current_token().value == "type"` for the `type:` field inside `graph_edge:`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphEdgeParsing -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_graph_semantics.py
git commit -m "feat(parser): parse graph_edge: blocks on entities (#619)"
```

---

### Task 4: Parser — `graph_node:` Block

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py`
- Test: `tests/unit/test_graph_semantics.py`

- [ ] **Step 1: Write failing test for graph_node parsing**

Append to `tests/unit/test_graph_semantics.py`:

```python
class TestGraphNodeParsing:
    """Parser recognizes graph_node: blocks."""

    def test_graph_node_with_display(self) -> None:
        dsl = '''
module test
app g "G"

entity Node "Node":
  id: uuid pk
  title: str(200) required

  graph_node:
    edges: NodeEdge
    display: title

entity NodeEdge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
'''
        appspec = _parse(dsl)
        node_entity = next(e for e in appspec.domain.entities if e.name == "Node")
        gn = node_entity.graph_node
        assert gn is not None
        assert gn.edge_entity == "NodeEdge"
        assert gn.display == "title"

    def test_graph_node_edges_only(self) -> None:
        dsl = '''
module test
app g "G"

entity Node "Node":
  id: uuid pk

  graph_node:
    edges: NodeEdge

entity NodeEdge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
'''
        appspec = _parse(dsl)
        node_entity = next(e for e in appspec.domain.entities if e.name == "Node")
        gn = node_entity.graph_node
        assert gn is not None
        assert gn.edge_entity == "NodeEdge"
        assert gn.display is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphNodeParsing -v`
Expected: FAIL — parser doesn't recognize `graph_node:`.

- [ ] **Step 3: Implement graph_node parsing**

In `src/dazzle/core/dsl_parser_impl/entity.py`, add after the `graph_edge:` parsing block:

```python
            # v0.46.0: Check for graph_node: block (#619)
            if self.match(TokenType.GRAPH_NODE):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                gn_edges: str | None = None
                gn_display: str | None = None

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    if self.match(TokenType.EDGES):
                        self.advance()
                        self.expect(TokenType.COLON)
                        gn_edges = self.expect_identifier_or_keyword().value
                    elif self.match(TokenType.DISPLAY):
                        self.advance()
                        self.expect(TokenType.COLON)
                        gn_display = self.expect_identifier_or_keyword().value
                    else:
                        raise make_parse_error(
                            f"Unexpected token in graph_node: block: {self.current_token().value}",
                            self.file,
                            self.current_token().line,
                        )
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

                if gn_edges is None:
                    raise make_parse_error(
                        "graph_node: requires an edges field",
                        self.file,
                        self.current_token().line,
                    )

                graph_node = ir.GraphNodeSpec(
                    edge_entity=gn_edges,
                    display=gn_display,
                )
                self.skip_newlines()
                continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphNodeParsing -v`
Expected: 2 PASSED.

- [ ] **Step 5: Run all parser tests for regressions**

Run: `pytest tests/unit/test_parser.py -x -q`
Expected: 111 passed.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_graph_semantics.py
git commit -m "feat(parser): parse graph_node: blocks on entities (#619)"
```

---

### Task 5: Validator — Hard Errors

**Files:**
- Modify: `src/dazzle/core/validator.py` (add `validate_graph_declarations()`)
- Modify: `src/dazzle/core/lint.py` (wire it in)
- Test: `tests/unit/test_graph_semantics.py`

- [ ] **Step 1: Write failing tests for graph validation errors**

Append to `tests/unit/test_graph_semantics.py`:

```python
from dazzle.core.validator import validate_graph_declarations


def _make_entity(
    name: str,
    fields: list[ir.FieldSpec] | None = None,
    graph_edge: ir.GraphEdgeSpec | None = None,
    graph_node: ir.GraphNodeSpec | None = None,
) -> ir.EntitySpec:
    """Helper to build a minimal entity."""
    default_fields = [
        ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
    ]
    return ir.EntitySpec(
        name=name,
        fields=fields or default_fields,
        graph_edge=graph_edge,
        graph_node=graph_node,
    )


def _make_appspec(entities: list[ir.EntitySpec]) -> ir.AppSpec:
    """Helper to build a minimal AppSpec."""
    return ir.AppSpec(
        module_name="test",
        app_name="test",
        app_title="Test",
        domain=ir.DomainSpec(entities=entities),
        surfaces=[],
    )


class TestGraphValidationErrors:
    """Hard errors that block app startup."""

    def test_source_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("source 'src' is not a field on Edge" in e for e in errors)

    def test_target_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("target 'tgt' is not a field on Edge" in e for e in errors)

    def test_source_not_ref_type(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(name="src", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("source must be a ref field, got 'str'" in e for e in errors)

    def test_weight_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(
                source="src", target="tgt", weight_field="importance"
            ),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("weight 'importance' is not a field on Edge" in e for e in errors)

    def test_target_not_ref_type(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(name="tgt", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("target must be a ref field, got 'str'" in e for e in errors)

    def test_weight_field_not_numeric(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="importance", type=ir.FieldType(kind=ir.FieldTypeKind.STR)
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(
                source="src", target="tgt", weight_field="importance"
            ),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("weight must be int or decimal" in e for e in errors)

    def test_type_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(
                source="src", target="tgt", type_field="kind"
            ),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("type 'kind' is not a field on Edge" in e for e in errors)

    def test_graph_node_edges_nonexistent_entity(self) -> None:
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="FakeEdge"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node]))
        assert any("edges 'FakeEdge' is not a defined entity" in e for e in errors)

    def test_graph_node_edges_entity_has_no_graph_edge(self) -> None:
        edge = _make_entity("EdgeEntity")  # no graph_edge
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="EdgeEntity"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node, edge]))
        assert any(
            "does not declare graph_edge:" in e for e in errors
        )

    def test_graph_node_display_field_not_found(self) -> None:
        edge = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="Edge", display="nonexistent"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node, edge]))
        assert any("display 'nonexistent' is not a field on Node" in e for e in errors)

    def test_valid_graph_no_errors(self) -> None:
        node = _make_entity(
            "Node",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="title", type=ir.FieldType(kind=ir.FieldTypeKind.STR)
                ),
            ],
            graph_node=ir.GraphNodeSpec(edge_entity="Edge", display="title"),
        )
        edge = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node, edge]))
        assert errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphValidationErrors -v`
Expected: FAIL — `validate_graph_declarations` does not exist.

- [ ] **Step 3: Implement validate_graph_declarations**

Add to `src/dazzle/core/validator.py`:

```python
# Numeric field types for graph weight validation
_NUMERIC_FIELD_TYPES = frozenset({
    ir.FieldTypeKind.INT,
    ir.FieldTypeKind.DECIMAL,
})


def validate_graph_declarations(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate graph_edge: and graph_node: declarations.

    Checks field references, types, and cross-entity consistency.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    entity_map = {e.name: e for e in appspec.domain.entities}

    for entity in appspec.domain.entities:
        if entity.graph_edge is not None:
            _validate_graph_edge(entity, entity_map, errors, warnings)
        if entity.graph_node is not None:
            _validate_graph_node(entity, entity_map, errors, warnings)

    return errors, warnings


def _validate_graph_edge(
    entity: ir.EntitySpec,
    entity_map: dict[str, ir.EntitySpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a single entity's graph_edge: block."""
    ge = entity.graph_edge
    assert ge is not None
    field_map = {f.name: f for f in entity.fields}

    # source field
    if ge.source not in field_map:
        errors.append(
            f"graph_edge source '{ge.source}' is not a field on {entity.name}"
        )
    else:
        src_field = field_map[ge.source]
        if src_field.type.kind != ir.FieldTypeKind.REF:
            errors.append(
                f"graph_edge source must be a ref field, got '{src_field.type.kind.value}'"
            )

    # target field
    if ge.target not in field_map:
        errors.append(
            f"graph_edge target '{ge.target}' is not a field on {entity.name}"
        )
    else:
        tgt_field = field_map[ge.target]
        if tgt_field.type.kind != ir.FieldTypeKind.REF:
            errors.append(
                f"graph_edge target must be a ref field, got '{tgt_field.type.kind.value}'"
            )

    # type_field (optional)
    if ge.type_field is not None:
        if ge.type_field not in field_map:
            errors.append(
                f"graph_edge type '{ge.type_field}' is not a field on {entity.name}"
            )

    # weight_field (optional)
    if ge.weight_field is not None:
        if ge.weight_field not in field_map:
            errors.append(
                f"graph_edge weight '{ge.weight_field}' is not a field on {entity.name}"
            )
        else:
            wf = field_map[ge.weight_field]
            if wf.type.kind not in _NUMERIC_FIELD_TYPES:
                errors.append(
                    f"graph_edge weight must be int or decimal"
                )

    # Warnings: heterogeneous graph, no access control
    if ge.source in field_map and ge.target in field_map:
        src_ref = field_map[ge.source].type.ref_entity
        tgt_ref = field_map[ge.target].type.ref_entity
        if src_ref and tgt_ref and src_ref != tgt_ref:
            warnings.append(
                f"Heterogeneous graph: source refs {src_ref}, target refs {tgt_ref}"
            )

    if entity.access is None or not entity.access.permissions:
        warnings.append(f"Edge entity '{entity.name}' has no access control")

    if ge.acyclic:
        warnings.append(
            f"acyclic declared but cycles only detected in seed data"
        )


def _validate_graph_node(
    entity: ir.EntitySpec,
    entity_map: dict[str, ir.EntitySpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a single entity's graph_node: block."""
    gn = entity.graph_node
    assert gn is not None

    if gn.edge_entity not in entity_map:
        errors.append(
            f"graph_node edges '{gn.edge_entity}' is not a defined entity"
        )
    else:
        edge_ent = entity_map[gn.edge_entity]
        if edge_ent.graph_edge is None:
            errors.append(
                f"graph_node edges '{gn.edge_entity}' does not declare graph_edge:"
            )

    if gn.display is not None:
        field_map = {f.name: f for f in entity.fields}
        if gn.display not in field_map:
            errors.append(
                f"graph_node display '{gn.display}' is not a field on {entity.name}"
            )
    else:
        warnings.append(
            f"graph_node has no display field — labels use default fallback"
        )
```

- [ ] **Step 4: Wire into lint.py**

In `src/dazzle/core/lint.py`, add `validate_graph_declarations` to the import block:

```python
from .validator import (
    ...
    validate_graph_declarations,
)
```

And add the call in `lint_appspec()` (after `validate_scope_predicates`):

```python
    # Graph semantics validation (v0.46.0 — #619)
    errors, warnings = validate_graph_declarations(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphValidationErrors -v`
Expected: 10 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/validator.py src/dazzle/core/lint.py tests/unit/test_graph_semantics.py
git commit -m "feat(validator): validate graph_edge/graph_node declarations (#619)"
```

---

### Task 6: Validator — Warnings + Lint Hints

**Files:**
- Modify: `src/dazzle/core/validator.py` (add lint hint to `extended_lint`)
- Test: `tests/unit/test_graph_semantics.py`

- [ ] **Step 1: Write failing tests for warnings and lint hints**

Append to `tests/unit/test_graph_semantics.py`:

```python
class TestGraphValidationWarnings:
    """Advisory warnings (non-blocking)."""

    def test_heterogeneous_graph_warning(self) -> None:
        edge = _make_entity(
            "AuthorWork",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="author",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Author"),
                ),
                ir.FieldSpec(
                    name="work",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Work"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="author", target="work"),
        )
        author = _make_entity("Author")
        work = _make_entity("Work")
        _, warnings = validate_graph_declarations(
            _make_appspec([author, work, edge])
        )
        assert any("Heterogeneous graph" in w for w in warnings)

    def test_no_access_control_warning(self) -> None:
        edge = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        _, warnings = validate_graph_declarations(_make_appspec([node, edge]))
        assert any("no access control" in w for w in warnings)

    def test_graph_node_no_display_warning(self) -> None:
        edge = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="Edge"),
        )
        _, warnings = validate_graph_declarations(_make_appspec([node, edge]))
        assert any("no display field" in w for w in warnings)

    def test_acyclic_warning(self) -> None:
        edge = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt", acyclic=True),
        )
        node = _make_entity("Node")
        _, warnings = validate_graph_declarations(_make_appspec([node, edge]))
        assert any("acyclic declared" in w for w in warnings)


class TestGraphLintHints:
    """Extended lint suggestions for graph patterns."""

    def test_entity_looks_like_edge_hint(self) -> None:
        """Entity with 2+ refs to the same entity should suggest graph_edge:."""
        from dazzle.core.validator import extended_lint

        entity = _make_entity(
            "NodeEdge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="source_node",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="target_node",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
        )
        node = _make_entity("Node")
        appspec = _make_appspec([node, entity])
        warnings = extended_lint(appspec)
        assert any("looks like a graph edge" in w for w in warnings)

    def test_no_hint_when_graph_edge_present(self) -> None:
        """No suggestion if entity already has graph_edge:."""
        from dazzle.core.validator import extended_lint

        entity = _make_entity(
            "NodeEdge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="source_node",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="target_node",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="source_node", target="target_node"),
        )
        node = _make_entity("Node")
        appspec = _make_appspec([node, entity])
        warnings = extended_lint(appspec)
        assert not any("looks like a graph edge" in w for w in warnings)

    def test_suggest_graph_node_on_target(self) -> None:
        """Edge entity targeting Node without graph_node: triggers hint."""
        from dazzle.core.validator import extended_lint

        edge = _make_entity(
            "NodeEdge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")  # no graph_node
        appspec = _make_appspec([node, edge])
        warnings = extended_lint(appspec)
        assert any("consider adding graph_node:" in w for w in warnings)

    def test_no_graph_node_hint_when_present(self) -> None:
        """No suggestion if target entity already has graph_node:."""
        from dazzle.core.validator import extended_lint

        edge = _make_entity(
            "NodeEdge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="NodeEdge"),
        )
        appspec = _make_appspec([node, edge])
        warnings = extended_lint(appspec)
        assert not any("consider adding graph_node:" in w for w in warnings)
```

- [ ] **Step 2: Run tests to verify lint hint tests fail**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphLintHints -v`
Expected: FAIL — `extended_lint` doesn't produce graph hints yet.

- [ ] **Step 3: Add lint hint to extended_lint**

In `src/dazzle/core/validator.py`, add a new function:

```python
def _lint_graph_edge_suggestions(appspec: ir.AppSpec) -> list[str]:
    """Suggest graph_edge: for entities with 2+ ref fields to the same entity."""
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        if entity.graph_edge is not None:
            continue
        ref_targets: dict[str, int] = {}
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
                ref_targets[field.type.ref_entity] = (
                    ref_targets.get(field.type.ref_entity, 0) + 1
                )
        for target, count in ref_targets.items():
            if count >= 2:
                warnings.append(
                    f"Entity '{entity.name}' looks like a graph edge — "
                    f"has {count} ref fields to '{target}'. "
                    f"Consider adding graph_edge:"
                )
                break
    return warnings


def _lint_graph_node_suggestions(appspec: ir.AppSpec) -> list[str]:
    """Suggest graph_node: for entities targeted by graph_edge: declarations."""
    warnings: list[str] = []
    entity_map = {e.name: e for e in appspec.domain.entities}
    for entity in appspec.domain.entities:
        if entity.graph_edge is None:
            continue
        field_map = {f.name: f for f in entity.fields}
        for field_name in (entity.graph_edge.source, entity.graph_edge.target):
            field = field_map.get(field_name)
            if field and field.type.ref_entity:
                target_ent = entity_map.get(field.type.ref_entity)
                if target_ent and target_ent.graph_node is None:
                    warnings.append(
                        f"'{entity.name}' targets '{target_ent.name}' — "
                        f"consider adding graph_node: for discoverability"
                    )
    return warnings
```

Wire both into `extended_lint`:

```python
    warnings.extend(_lint_graph_edge_suggestions(appspec))
    warnings.extend(_lint_graph_node_suggestions(appspec))
```

- [ ] **Step 4: Run all graph semantics tests**

Run: `pytest tests/unit/test_graph_semantics.py -v`
Expected: All PASSED (6 + 3 + 2 + 12 + 4 + 4 = 31 tests).

- [ ] **Step 5: Run full test suite for regressions**

Run: `pytest tests/unit/test_parser.py tests/unit/test_validator.py -x -q`
Expected: All existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/validator.py tests/unit/test_graph_semantics.py
git commit -m "feat(lint): graph warnings and edge-suggestion lint hints (#619)"
```

---

### Task 7: Integration Test — Full Round-Trip

**Files:**
- Test: `tests/unit/test_graph_semantics.py`

- [ ] **Step 1: Write full round-trip test**

Append to `tests/unit/test_graph_semantics.py`:

```python
class TestGraphRoundTrip:
    """Full DSL → parse → validate round-trip."""

    def test_full_graph_declaration(self) -> None:
        """Penny Dreadful-style graph: nodes + edges + heterogeneous."""
        dsl = '''
module test
app g "G"

entity Node "Node":
  id: uuid pk
  title: str(200) required
  content: text

  graph_node:
    edges: NodeEdge
    display: title

entity NodeEdge "Edge":
  id: uuid pk
  source_node: ref Node required
  target_node: ref Node required
  relationship: enum[sequel,fork,reference,adaptation]
  importance: int optional

  graph_edge:
    source: source_node
    target: target_node
    type: relationship
    weight: importance
    directed: true
    acyclic: false
'''
        appspec = _parse(dsl)

        # Parse check
        node_e = next(e for e in appspec.domain.entities if e.name == "Node")
        edge_e = next(e for e in appspec.domain.entities if e.name == "NodeEdge")
        assert node_e.graph_node is not None
        assert edge_e.graph_edge is not None
        assert edge_e.graph_edge.type_field == "relationship"
        assert edge_e.graph_edge.weight_field == "importance"
        assert node_e.graph_node.display == "title"

        # Validate — should produce no errors
        errors, _ = validate_graph_declarations(appspec)
        assert errors == []

    def test_bipartite_graph(self) -> None:
        """Heterogeneous graph with different node types."""
        dsl = '''
module test
app g "G"

entity Author "Author":
  id: uuid pk
  name: str(200) required

entity Work "Work":
  id: uuid pk
  title: str(200) required

entity AuthorWork "Author-Work Link":
  id: uuid pk
  author: ref Author required
  work: ref Work required
  role: enum[creator,editor,contributor]

  graph_edge:
    source: author
    target: work
    type: role
'''
        appspec = _parse(dsl)
        aw = next(e for e in appspec.domain.entities if e.name == "AuthorWork")
        assert aw.graph_edge is not None
        assert aw.graph_edge.source == "author"
        assert aw.graph_edge.target == "work"

        errors, warnings = validate_graph_declarations(appspec)
        assert errors == []
        assert any("Heterogeneous graph" in w for w in warnings)
```

- [ ] **Step 2: Run the round-trip tests**

Run: `pytest tests/unit/test_graph_semantics.py::TestGraphRoundTrip -v`
Expected: 2 PASSED.

- [ ] **Step 3: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All pass (existing + 33 new).

- [ ] **Step 4: Run linting and type checks**

Run: `ruff check src/dazzle/core/ir/domain.py src/dazzle/core/lexer.py src/dazzle/core/dsl_parser_impl/entity.py src/dazzle/core/validator.py src/dazzle/core/lint.py --fix && ruff format src/dazzle/core/ tests/unit/test_graph_semantics.py`
Run: `mypy src/dazzle/core/ir/domain.py src/dazzle/core/validator.py`
Expected: Clean.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_graph_semantics.py
git commit -m "test: graph semantics round-trip integration tests (#619)"
```

---

### Task 8: Grammar Documentation

**Files:**
- Modify: `docs/reference/grammar.md` (add graph constructs)

- [ ] **Step 1: Add graph_edge and graph_node to grammar reference**

Append to the entity section of `docs/reference/grammar.md`:

```markdown
### Graph Semantics (v0.46.0)

#### graph_edge: (on entity)

Declares that this entity represents edges in a directed property graph.

```
graph_edge:
  source: <ref_field_name>       # required
  target: <ref_field_name>       # required
  type: <field_name>             # optional — edge type discriminator
  weight: <numeric_field_name>   # optional — weight for algorithms
  directed: true|false           # optional — default true
  acyclic: true|false            # optional — default false
```

#### graph_node: (on entity)

Optional annotation declaring this entity as a node in a graph.

```
graph_node:
  edges: <edge_entity_name>      # required — the edge entity
  display: <field_name>          # optional — label field
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/reference/grammar.md
git commit -m "docs: add graph_edge/graph_node to grammar reference (#619)"
```
