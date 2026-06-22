# `poly_ref` Polymorphic-Ref Scoping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a typed `poly_ref` field primitive + a `target[Type].path` scope-path selector so polymorphic platform-entity references can be declaratively, securely scoped to non-admin roles — with a `dazzle db explain-scope` traceability oracle.

**Architecture:** A `poly_ref name [T1, T2]` field owns two physical columns (`name_type text`, `name_id uuid`). The FK graph learns conditional branch edges so `name[T1].sub` resolves as a real path. The scope compiles to `"name_type" = 'T1' AND "name_id" IN (SELECT id FROM t1 WHERE <sub>)` — reusing the existing `ExistsCheck`/`PathCheck` subquery machinery in both app-layer (param) and RLS (policy) modes, degrading to app-layer via the shipped #1447 path when the sub-predicate isn't RLS-expressible.

**Tech Stack:** Python 3.12+, Pydantic IR, SQLAlchemy (`sa_schema`), psycopg3, Typer CLI, pytest (unit + real-PG integration).

**Spec:** `docs/superpowers/specs/2026-06-22-polymorphic-ref-scoping-1448-design.md` (#1448).

## Global Constraints

- **No regex in the lexer/parser** (ADR-0024) — token dispatch only.
- **No new singletons** (ADR-0005); **clean breaks, no shims** (ADR-0003).
- **All schema changes via Alembic** (ADR-0017) — but the new fixture entity is created by the normal boot DDL (`build_metadata` → `create_all`) on the scratch test DB; no committed-app migration is in scope.
- **poly_ref targets must be uuid-pk entities** (the Dazzle default) — this is what lets `name_id` be a real `uuid` with no `::uuid` cast anywhere.
- **Type hints required** on all public functions (mypy). **No `from __future__ import annotations` in FastAPI route files** (ADR-0014) — not relevant to the files here, but `predicates.py`/`fields.py` already carry it; keep it.
- Predicate compiler return type is **`tuple[str, list[Any]]`** (SQL fragment + positional params/markers); policy mode returns a **bare `str`** and must produce **zero** params.
- Ship discipline: `/bump patch` before pushing; pre-commit runs `ruff format` (format touched files BEFORE committing or the hook aborts).

---

### Task 1: IR — `poly_ref` field kind + `PolyPathCheck` predicate node

**Files:**
- Modify: `src/dazzle/core/ir/fields.py:21-68` (FieldTypeKind), `:108-123` (FieldType)
- Modify: `src/dazzle/core/ir/predicates.py:196-212` (after ExistsCheck), `:307-317` (union)
- Test: `tests/unit/test_poly_ref_ir.py` (create)

**Interfaces:**
- Produces: `FieldTypeKind.POLY_REF`; `FieldType.poly_targets: list[str] | None`; `PolyPathCheck` node with fields `kind: Literal["poly_path"]`, `field: str`, `type_field: str`, `type_value: str`, `id_field: str`, `target_entity: str`, `sub: ScopePredicate`. Later tasks consume all of these.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_ir.py
from pydantic import TypeAdapter

from dazzle.core.ir.fields import FieldType, FieldTypeKind
from dazzle.core.ir.predicates import (
    PolyPathCheck,
    ScopePredicate,
    UserAttrCheck,
    CompOp,
)


def test_poly_ref_field_type():
    ft = FieldType(kind=FieldTypeKind.POLY_REF, poly_targets=["CohortAssessment", "Manuscript"])
    assert ft.kind == FieldTypeKind.POLY_REF
    assert ft.poly_targets == ["CohortAssessment", "Manuscript"]


def test_poly_path_check_in_union():
    node = PolyPathCheck(
        field="target",
        type_field="target_type",
        type_value="CohortAssessment",
        id_field="target_id",
        target_entity="CohortAssessment",
        sub=UserAttrCheck(field="uploaded_by", op=CompOp.EQ, user_attr="entity_id"),
    )
    # Round-trips through the discriminated union on the "kind" tag.
    adapter = TypeAdapter(ScopePredicate)
    restored = adapter.validate_python(node.model_dump())
    assert isinstance(restored, PolyPathCheck)
    assert restored.target_entity == "CohortAssessment"
    assert restored.sub.field == "uploaded_by"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_ir.py -q`
Expected: FAIL — `ImportError: cannot import name 'PolyPathCheck'` / `POLY_REF` not on FieldTypeKind.

- [ ] **Step 3: Add `POLY_REF` to FieldTypeKind + `poly_targets` to FieldType**

In `src/dazzle/core/ir/fields.py`, add to the `FieldTypeKind` enum (after `ANCESTORS_OF = "ancestors_of"`, line 67):

```python
    # #1448 — typed polymorphic reference. `poly_ref target [A, B]` owns two
    # physical columns (target_type text, target_id uuid) and replaces the
    # stringly-typed entity_type/entity_id pathology. Targets MUST be uuid-pk.
    POLY_REF = "poly_ref"
```

In `FieldType`, add after `via_entity` (line 123):

```python
    # #1448: for poly_ref — the ordered set of legal target entity names.
    poly_targets: list[str] | None = None
```

- [ ] **Step 4: Add `PolyPathCheck` node + register in the union**

In `src/dazzle/core/ir/predicates.py`, add after `ExistsCheck` (line 212):

```python
class PolyPathCheck(BaseModel):
    """Scope through one branch of a typed polymorphic ref (#1448).

    For ``target[CohortAssessment].uploaded_by = current_user`` on an entity
    with ``poly_ref target [CohortAssessment, Manuscript]`` this models::

        "target_type" = 'CohortAssessment'
        AND "target_id" IN (SELECT id FROM cohort_assessment WHERE <sub>)

    ``sub`` is an ordinary predicate rooted on ``target_entity`` (here a
    ``UserAttrCheck`` for ``uploaded_by = current_user``). No cast: ``id_field``
    is a real ``uuid`` column.
    """

    kind: Literal["poly_path"] = "poly_path"
    field: str           # the poly_ref field name, e.g. "target"
    type_field: str      # f"{field}_type"
    type_value: str      # selected branch, e.g. "CohortAssessment"
    id_field: str        # f"{field}_id"
    target_entity: str   # == type_value (the resolved entity)
    sub: ScopePredicate  # post-selector predicate, rooted on target_entity

    model_config = ConfigDict(frozen=True)
```

Add `PolyPathCheck` to the union (line 307-317):

```python
ScopePredicate = Annotated[
    ColumnCheck
    | ColumnRefCheck
    | UserAttrCheck
    | PathCheck
    | ExistsCheck
    | PolyPathCheck
    | BoolComposite
    | Tautology
    | Contradiction,
    Field(discriminator="kind"),
]
```

Add a `model_rebuild()` after the union so the forward ref in `sub` resolves (next to the existing `BoolComposite.model_rebuild()` at line 329):

```python
PolyPathCheck.model_rebuild()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_poly_ref_ir.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
ruff format src/dazzle/core/ir/fields.py src/dazzle/core/ir/predicates.py tests/unit/test_poly_ref_ir.py
git add src/dazzle/core/ir/fields.py src/dazzle/core/ir/predicates.py tests/unit/test_poly_ref_ir.py
git commit -m "feat(ir): #1448 poly_ref field kind + PolyPathCheck predicate node"
```

---

### Task 2: Lexer — `POLY_REF` token

**Files:**
- Modify: `src/dazzle/core/lexer.py:298-315` (relationship keywords block)
- Test: `tests/unit/test_poly_ref_parser.py` (create — shared with Task 3)

**Interfaces:**
- Produces: `TokenType.POLY_REF` (value `"poly_ref"`), auto-registered as a keyword by the existing `KEYWORDS` frozenset comprehension (lexer.py:725).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_parser.py
from dazzle.core.lexer import Lexer, TokenType


def test_poly_ref_tokenizes_as_keyword():
    toks = Lexer("poly_ref target [A, B]").tokenize()
    kinds = [t.type for t in toks]
    assert TokenType.POLY_REF in kinds
    assert TokenType.LBRACKET in kinds
    assert TokenType.RBRACKET in kinds
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_parser.py::test_poly_ref_tokenizes_as_keyword -q`
Expected: FAIL — `AttributeError: POLY_REF` (or `poly_ref` lexes as IDENTIFIER, assertion fails).

- [ ] **Step 3: Add the token**

In `src/dazzle/core/lexer.py`, in the relationship-keywords block (after `BELONGS_TO = "belongs_to"`, line ~308):

```python
    # #1448: typed polymorphic reference field type
    POLY_REF = "poly_ref"
```

(No keyword-map edit needed — `KEYWORDS` at line 725 is generated from the enum.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_poly_ref_parser.py::test_poly_ref_tokenizes_as_keyword -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/core/lexer.py tests/unit/test_poly_ref_parser.py
git add src/dazzle/core/lexer.py tests/unit/test_poly_ref_parser.py
git commit -m "feat(lexer): #1448 POLY_REF token"
```

---

### Task 3: Parser — `poly_ref [T1, T2]` field-type declaration

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/types.py:114-165` (dispatch), add `_parse_poly_ref_type`
- Test: `tests/unit/test_poly_ref_parser.py` (extend)

**Interfaces:**
- Consumes: `TokenType.POLY_REF`, `FieldTypeKind.POLY_REF`, `FieldType.poly_targets` (Task 1, 2).
- Produces: a parsed `poly_ref name [A, B]` field whose `field.type` is `FieldType(kind=POLY_REF, poly_targets=[...])`. The field *name* is consumed by the existing field-declaration caller; this parser handles the type portion (`poly_ref [A, B]`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_parser.py  (append)
from dazzle.core.parser import parse_dsl   # whatever the top-level parse entry is

_SRC = """
module m
app a "A"

entity Cohort "Cohort":
  id: uuid pk
  name: str(80)

entity AIJob "AI Job":
  id: uuid pk
  target: poly_ref [Cohort]
"""


def test_parse_poly_ref_field():
    appspec = parse_dsl(_SRC)            # adjust to the real entry signature
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    target = next(f for f in aijob.fields if f.name == "target")
    assert target.type.kind.value == "poly_ref"
    assert target.type.poly_targets == ["Cohort"]
```

> Note: confirm the real top-level parse entry (grep `def parse_dsl` / `Parser(`); mirror an existing `tests/unit/test_parser.py` entity test for the exact call. Use that call here.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_parser.py::test_parse_poly_ref_field -q`
Expected: FAIL — type parser doesn't recognise `poly_ref` (parse error or wrong kind).

- [ ] **Step 3: Add `_parse_poly_ref_type` + dispatch entry**

In `src/dazzle/core/dsl_parser_impl/types.py`, add the parser method (mirror `_parse_belongs_to_type` at line 421):

```python
    def _parse_poly_ref_type(self) -> ir.FieldType:
        """Parse `poly_ref [Target1, Target2, ...]` (#1448)."""
        self.advance()  # consume 'poly_ref'
        self.expect(TokenType.LBRACKET)
        targets: list[str] = []
        while not self.match(TokenType.RBRACKET):
            targets.append(self.expect(TokenType.IDENTIFIER).value)
            if self.match(TokenType.COMMA):
                self.advance()
        self.expect(TokenType.RBRACKET)
        if not targets:
            raise make_parse_error(
                "poly_ref requires at least one target entity, e.g. "
                "`poly_ref target [CohortAssessment]`",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )
        return ir.FieldType(kind=ir.FieldTypeKind.POLY_REF, poly_targets=targets)
```

> `make_parse_error` is already imported in this module if used elsewhere; if not, add `from ..errors import make_parse_error`. Confirm `self.file` exists on the parser (it does on `BaseParser`).

Register it in the **value dispatch** table in `parse_type_spec` (line ~145, next to `"ref": self._parse_ref_type`):

```python
            "poly_ref": self._parse_poly_ref_type,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_poly_ref_parser.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/core/dsl_parser_impl/types.py tests/unit/test_poly_ref_parser.py
git add src/dazzle/core/dsl_parser_impl/types.py tests/unit/test_poly_ref_parser.py
git commit -m "feat(parser): #1448 parse poly_ref [Targets] field type"
```

---

### Task 4: Schema — `poly_ref` field → two columns (`_type` text, `_id` uuid)

**Files:**
- Modify: `src/dazzle/http/runtime/sa_schema.py:563-567` (the `for field in entity.fields` column loop in `build_metadata`)
- Test: `tests/unit/test_poly_ref_schema.py` (create)

**Interfaces:**
- Consumes: `FieldTypeKind.POLY_REF`, `FieldType.poly_targets`.
- Produces: for a `poly_ref name [...]` field, two SQLAlchemy columns `name_type` (`sa.Text()`, not null) and `name_id` (`sa.Uuid()`, not null). No FK constraint (the ref is polymorphic). Optional poly_ref (`poly_ref?`) → both nullable; the MVP supports required only (parser emits required), nullable is a noted follow-on.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_schema.py
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.domain import EntitySpec
from dazzle.http.runtime.sa_schema import build_metadata


def _entity_with_poly():
    # Mirror however EntitySpec/FieldSpec are constructed in tests/unit/test_sa_schema*.py
    return EntitySpec(
        name="AIJob",
        label="AI Job",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID), is_required=True),
            FieldSpec(
                name="target",
                type=FieldType(kind=FieldTypeKind.POLY_REF, poly_targets=["Cohort"]),
                is_required=True,
            ),
        ],
    )


def test_poly_ref_emits_two_columns():
    md = build_metadata([_entity_with_poly()])
    table = md.tables["AIJob"]
    assert "target_type" in table.columns
    assert "target_id" in table.columns
    assert "target" not in table.columns  # the logical field has no own column
    assert str(table.columns["target_id"].type).upper().startswith("UUID")
    assert table.columns["target_type"].nullable is False
    assert table.columns["target_id"].nullable is False
```

> Confirm the real `EntitySpec`/`FieldSpec` constructor kwargs from `tests/unit/test_sa_schema*.py` (grep `build_metadata(` in tests) and copy that exact construction shape.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_schema.py -q`
Expected: FAIL — `_field_to_column` emits one column named `target` (or errors on the poly kind).

- [ ] **Step 3: Special-case poly_ref in the column loop**

In `src/dazzle/http/runtime/sa_schema.py`, replace the field loop body (lines 563-567):

```python
        for field in entity.fields:
            if field.type.kind == FieldTypeKind.POLY_REF:
                # #1448: one logical poly_ref → two physical columns. No FK (the
                # ref is polymorphic); target_id is a real uuid (targets are
                # uuid-pk), so no cast is ever needed downstream.
                required = bool(
                    getattr(field, "is_required", None) or getattr(field, "required", False)
                )
                columns.append(sa.Column(f"{field.name}_type", sa.Text(), nullable=not required))
                columns.append(sa.Column(f"{field.name}_id", sa.Uuid(), nullable=not required))
                continue
            columns.append(
                _field_to_column(
                    field,
                    entity.name,
```

Add the import near the top of `sa_schema.py` if not present:

```python
from dazzle.core.ir.fields import FieldTypeKind
```

> The table-per-type subtype branch (line 522-527) also calls `_field_to_column`; poly_ref on a subtype is out of MVP scope — leave that branch unchanged (a poly_ref on a subtype entity raises in `_field_to_column`'s default, which is acceptable for MVP; note it in CHANGELOG non-goals).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_poly_ref_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/http/runtime/sa_schema.py tests/unit/test_poly_ref_schema.py
git add src/dazzle/http/runtime/sa_schema.py tests/unit/test_poly_ref_schema.py
git commit -m "feat(schema): #1448 poly_ref → {name}_type text + {name}_id uuid columns"
```

---

### Task 5: Parser — `target[Type].path` scope-path selector

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/conditions.py` (`_parse_comparison`, the dotted-path section ~lines 60-80 of the function)
- Test: `tests/unit/test_poly_ref_scope_parse.py` (create)

**Interfaces:**
- Produces: a scope `Comparison` whose `field` string carries the selector inline as `"target[CohortAssessment].uploaded_by"`. Task 6 (predicate builder) consumes this string form.

**Why string-encode:** the condition parser has no field-type context (it runs before the FK graph is built), and the existing dotted-path machinery already flows paths as strings (`field = f"{field}.{next_part}"`). Encoding the selector inline keeps the change to one parser branch; the structured resolution happens in Task 6 where the entity + fk_graph context exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_scope_parse.py
from dazzle.core.dsl_parser_impl.conditions import ConditionParserMixin  # adjust to real entry

# Easiest: parse a full entity with the scope and inspect the raw ConditionExpr.
from dazzle.core.parser import parse_dsl

_SRC = """
module m
app a "A"

entity Cohort "Cohort":
  id: uuid pk
  uploaded_by: uuid

entity AIJob "AI Job":
  id: uuid pk
  target: poly_ref [Cohort]
  permit: read as: teacher
  scope: read: target[Cohort].uploaded_by = current_user as: teacher
"""


def test_scope_path_captures_type_selector():
    appspec = parse_dsl(_SRC)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    rule = aijob.access.scopes[0]
    # Before predicate-building, the parsed condition's field carries the selector.
    cond = rule.condition           # ConditionExpr
    assert cond.comparison.field == "target[Cohort].uploaded_by"
```

> Confirm where the parsed (pre-build) `condition` lives on the scope rule (it may be `rule.condition`); if the linker builds the predicate immediately, assert on the predicate instead (Task 6 covers that). Adjust the assertion to the real intermediate shape — grep `ScopeRule` / `access.scopes` in `tests/unit/test_scope_rules.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_scope_parse.py -q`
Expected: FAIL — parser errors on `[` after `target`, or drops the selector.

- [ ] **Step 3: Capture the `[Type]` selector in `_parse_comparison`**

In `src/dazzle/core/dsl_parser_impl/conditions.py`, in the dotted-path section of `_parse_comparison` (where `field = name` then the `while self.match(TokenType.DOT)` loop), insert a bracket-selector capture **before** the dot loop:

```python
            else:
                # Check for dotted path (owner.team) - v0.7.0
                field = name
                # #1448: poly_ref branch selector — `target[CohortAssessment].…`
                if self.match(TokenType.LBRACKET):
                    self.advance()
                    type_ident = self.expect(TokenType.IDENTIFIER).value
                    self.expect(TokenType.RBRACKET)
                    field = f"{field}[{type_ident}]"
                while self.match(TokenType.DOT):
                    self.advance()
                    next_part = self.expect_identifier_or_keyword().value
                    field = f"{field}.{next_part}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_poly_ref_scope_parse.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/core/dsl_parser_impl/conditions.py tests/unit/test_poly_ref_scope_parse.py
git add src/dazzle/core/dsl_parser_impl/conditions.py tests/unit/test_poly_ref_scope_parse.py
git commit -m "feat(parser): #1448 capture target[Type] poly-branch selector in scope paths"
```

---

### Task 6: Predicate builder — build `PolyPathCheck` from the encoded path

**Files:**
- Modify: `src/dazzle/core/ir/predicate_builder.py` (`build_scope_predicate`, the comparison section ~lines 145-165)
- Test: `tests/unit/test_poly_ref_predicate_build.py` (create)

**Interfaces:**
- Consumes: the `"target[Type].tail"` field string (Task 5); `FKGraph`; `PolyPathCheck`/`UserAttrCheck`/`PathCheck` (Task 1).
- Produces: a `PolyPathCheck` whose `sub` is the predicate the tail compiles to **rooted on the target entity** (e.g. `uploaded_by = current_user` → `UserAttrCheck(field="uploaded_by", user_attr="entity_id")`; a deeper tail → `PathCheck`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_predicate_build.py
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicate_builder import build_scope_predicate
from dazzle.core.ir.predicates import PolyPathCheck, UserAttrCheck
from dazzle.core.ir.conditions import ConditionExpr, Comparison  # adjust import to real module


def _cond(field: str, value: str) -> ConditionExpr:
    return ConditionExpr(comparison=Comparison(field=field, operator="=", value={"literal": value}))


def test_build_poly_path_check(simple_fk_graph):  # build an FKGraph with AIJob + Cohort(uuid pk)
    pred = build_scope_predicate(
        _cond("target[Cohort].uploaded_by", "current_user"),
        entity_name="AIJob",
        fk_graph=simple_fk_graph,
    )
    assert isinstance(pred, PolyPathCheck)
    assert pred.type_field == "target_type"
    assert pred.id_field == "target_id"
    assert pred.type_value == "Cohort"
    assert pred.target_entity == "Cohort"
    assert isinstance(pred.sub, UserAttrCheck)
    assert pred.sub.field == "uploaded_by"
```

> Build `simple_fk_graph` and the `Comparison`/`ConditionExpr` exactly as `tests/unit/test_predicate_builder.py` (grep it) constructs them — copy that fixture/shape. The `value` literal shape must match `_resolve_value_ref`'s expected input.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_predicate_build.py -q`
Expected: FAIL — builder splits on `.` and treats `target[Cohort]` as a literal segment → not a `PolyPathCheck`.

- [ ] **Step 3: Detect the selector and build the node**

In `src/dazzle/core/ir/predicate_builder.py`, in `build_scope_predicate`'s comparison branch, **before** the existing `if "." in field:` PathCheck handling, add:

```python
        # #1448: poly_ref branch — `target[CohortAssessment].tail`
        if "[" in field:
            head, _, rest = field.partition("[")
            type_value, _, after = rest.partition("]")
            tail = after[1:] if after.startswith(".") else after  # strip leading dot
            # Build the sub-predicate as if `tail <op> value` were rooted on the
            # target entity. Reuse this same builder by recursing on a synthetic
            # comparison with the post-selector path as its field.
            sub_cond = ConditionExpr(
                comparison=Comparison(field=tail, operator=cmp.operator, value=cmp.value)
            )
            sub = build_scope_predicate(sub_cond, type_value, fk_graph, entities_by_name)
            return PolyPathCheck(
                field=head,
                type_field=f"{head}_type",
                type_value=type_value,
                id_field=f"{head}_id",
                target_entity=type_value,
                sub=sub,
            )
```

Add `PolyPathCheck` to the imports at the top of the module (it imports the other predicate nodes already).

> `cmp.value` / `cmp.operator` names: confirm against the existing comparison handling in this function (the extractor showed `cmp = condition.comparison`, `op = _OP_MAP[cmp.operator]`, `raw_value = cmp.value.literal`). Pass `cmp.value` through unchanged so the recursion's own `_resolve_value_ref` handles `current_user`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_poly_ref_predicate_build.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/core/ir/predicate_builder.py tests/unit/test_poly_ref_predicate_build.py
git add src/dazzle/core/ir/predicate_builder.py tests/unit/test_poly_ref_predicate_build.py
git commit -m "feat(ir): #1448 build PolyPathCheck from target[Type].tail scope paths"
```

---

### Task 7: Validation — poly_ref scope checks (`E_POLY_*`)

**Files:**
- Modify: `src/dazzle/core/validation/rbac.py:126-192` (`_validate_predicate_node`)
- Test: `tests/unit/test_poly_ref_validation.py` (create)

**Interfaces:**
- Consumes: `PolyPathCheck`, the FK graph, the appspec (for uuid-pk + poly_targets lookups).
- Produces: four error families — `E_POLY_TARGET_NOT_UUID_PK`, `E_POLY_BRANCH_UNDECLARED`, `E_POLY_SELECTOR_REQUIRED`, plus delegation of `sub` validation to the existing per-node walk rooted on `target_entity`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_validation.py
from dazzle.core.parser import parse_dsl
from dazzle.core.validation.rbac import validate_scope_predicates

_OK = """
module m
app a "A"
entity Cohort "C":
  id: uuid pk
  uploaded_by: uuid
entity AIJob "J":
  id: uuid pk
  target: poly_ref [Cohort]
  permit: read as: teacher
  scope: read: target[Cohort].uploaded_by = current_user as: teacher
"""

_UNDECLARED = _OK.replace("target[Cohort].uploaded_by", "target[Manuscript].uploaded_by")
_NO_SELECTOR = _OK.replace("target[Cohort].uploaded_by", "target.uploaded_by")


def _errors(src: str) -> list[str]:
    appspec = parse_dsl(src)                       # adjust to whatever yields a linked AppSpec
    errs, _ = validate_scope_predicates(appspec)
    return errs


def test_poly_ok_has_no_errors():
    assert _errors(_OK) == []


def test_poly_branch_undeclared():
    assert any("Manuscript" in e for e in _errors(_UNDECLARED))


def test_poly_selector_required():
    assert any("selector" in e.lower() or "poly_ref" in e.lower() for e in _errors(_NO_SELECTOR))
```

> If `parse_dsl` doesn't build the FK graph + predicates, use the linker entry the other rbac tests use (grep `validate_scope_predicates` in `tests/unit/test_validate_scope_predicates.py`) so `appspec.fk_graph` and `rule.predicate` are populated.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_validation.py -q`
Expected: FAIL — no poly handling; undeclared/selector cases either pass silently or raise a confusing FK error.

- [ ] **Step 3: Handle `PolyPathCheck` in `_validate_predicate_node` + selector-required in the PathCheck branch**

In `src/dazzle/core/validation/rbac.py`, import `PolyPathCheck` in the local import block (line ~145) and add a branch:

```python
    if isinstance(node, PolyPathCheck):
        # Field must be a poly_ref on this entity.
        ent = next((e for e in appspec.domain.entities if e.name == entity_name), None)
        poly_field = next(
            (f for f in (ent.fields if ent else []) if f.name == node.field), None
        )
        targets = (poly_field.type.poly_targets or []) if poly_field else []
        if poly_field is None or poly_field.type.kind.value != "poly_ref":
            errors.append(
                f"{ctx}: E_POLY_SELECTOR_REQUIRED — '{node.field}' is not a poly_ref field on "
                f"'{entity_name}'"
            )
            return
        if node.type_value not in targets:
            errors.append(
                f"{ctx}: E_POLY_BRANCH_UNDECLARED — branch '{node.type_value}' is not a declared "
                f"target of {entity_name}.{node.field} (declared: {targets or 'none'})"
            )
            return
        # Target must exist and be uuid-pk.
        tgt = next((e for e in appspec.domain.entities if e.name == node.type_value), None)
        if tgt is None:
            errors.append(f"{ctx}: E_POLY_BRANCH_UNDECLARED — unknown entity '{node.type_value}'")
            return
        id_field = next((f for f in tgt.fields if f.name == "id"), None)
        if id_field is None or id_field.type.kind.value != "uuid":
            errors.append(
                f"{ctx}: E_POLY_TARGET_NOT_UUID_PK — poly_ref target '{node.type_value}' must have a "
                f"uuid primary key"
            )
            return
        # Validate the sub-predicate rooted on the target entity.
        tgt_field_names = {f.name for f in tgt.fields}
        _validate_predicate_node(
            node.sub, node.type_value, tgt_field_names, fk_graph, appspec,
            f"{ctx} (poly branch {node.type_value})", errors, warnings,
        )
        return
```

In the existing `PathCheck` branch, when `resolve_segment` fails because the first segment is a poly_ref field (a common author mistake: `target.uploaded_by` with no selector), upgrade the message. After the `except (ValueError, AttributeError) as exc:` that breaks the loop, add a poly-aware hint:

```python
                except (ValueError, AttributeError) as exc:
                    ent = next((e for e in appspec.domain.entities if e.name == current), None)
                    pf = next((f for f in (ent.fields if ent else []) if f.name == segment), None)
                    if pf is not None and pf.type.kind.value == "poly_ref":
                        errors.append(
                            f"{ctx}: E_POLY_SELECTOR_REQUIRED — '{segment}' is a poly_ref; write "
                            f"'{segment}[<TargetType>].…' to select a branch"
                        )
                    else:
                        errors.append(f"{ctx}: PathCheck path '{path_str}' — {exc}")
                    break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_poly_ref_validation.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/core/validation/rbac.py tests/unit/test_poly_ref_validation.py
git add src/dazzle/core/validation/rbac.py tests/unit/test_poly_ref_validation.py
git commit -m "feat(validation): #1448 poly_ref scope checks (uuid-pk, declared-branch, selector-required)"
```

---

### Task 8: App-layer compiler — `_compile_poly_path_check`

**Files:**
- Modify: `src/dazzle/http/runtime/predicate_compiler.py:1006-1063` (dispatch), add `_compile_poly_path_check`
- Test: `tests/unit/test_poly_ref_compile.py` (create)

**Interfaces:**
- Consumes: `PolyPathCheck`; `_compile_predicate_impl` (recurse on `sub`); `_qualify_table`, `quote_identifier`.
- Produces: param-mode SQL `"target_type" = %s AND "target_id" IN (SELECT "id" FROM <target> WHERE <sub>)`, params `[type_value, *sub_params]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_compile.py
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicates import PolyPathCheck, UserAttrCheck, CompOp
from dazzle.http.runtime.predicate_compiler import compile_predicate, CurrentUserRef


def test_compile_poly_path_check(simple_fk_graph):
    node = PolyPathCheck(
        field="target", type_field="target_type", type_value="Cohort",
        id_field="target_id", target_entity="Cohort",
        sub=UserAttrCheck(field="uploaded_by", op=CompOp.EQ, user_attr="entity_id"),
    )
    sql, params = compile_predicate(node, "AIJob", simple_fk_graph)
    assert '"target_type" = %s' in sql
    assert '"target_id" IN (SELECT "id" FROM' in sql
    assert '"uploaded_by"' in sql
    assert params[0] == "Cohort"
    assert any(isinstance(p, CurrentUserRef) for p in params)
```

> Build `simple_fk_graph` via `FKGraph.from_entities([...])` with `Cohort` carrying `uploaded_by` (grep `FKGraph.from_entities` usage in `tests/unit/test_predicate_compiler*.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_compile.py -q`
Expected: FAIL — `_compile_predicate_impl` hits the `case _:` and raises `TypeError: Unknown predicate type`.

- [ ] **Step 3: Add the compiler + dispatch case**

In `src/dazzle/http/runtime/predicate_compiler.py`, add the function (mirror `_compile_path_check` at 637 + `_compile_exists_check` at 781):

```python
def _compile_poly_path_check(
    predicate: PolyPathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
    policy: _PolicyCtx | None = None,
) -> tuple[str, list[Any]]:
    """Compile a PolyPathCheck (#1448): type-guard AND uuid `IN (SELECT …)`.

    Param mode::

        "target_type" = %s AND "target_id" IN (SELECT "id" FROM <target> WHERE <sub>)

    Policy mode inlines the type literal and emits the sub in policy form. If the
    sub isn't policy-expressible it raises ValueError → the verb degrades to the
    app layer via the #1447 path (build_rls_scope_policy_ddl).
    """
    target_table = _qualify_table(predicate.target_entity, schema)
    type_col = quote_identifier(predicate.type_field)
    id_col = quote_identifier(predicate.id_field)

    sub_sql, sub_params = _compile_predicate_impl(
        predicate.sub, predicate.target_entity, fk_graph, schema=schema, policy=policy
    )
    sub_where = sub_sql if sub_sql else "true"

    if policy is not None:
        # Param-free: inline the discriminator literal.
        type_guard = f"{type_col} = {_inline_sql_literal(predicate.type_value)}"
        sql = f'{type_guard} AND {id_col} IN (SELECT "id" FROM {target_table} WHERE {sub_where})'
        return sql, []

    type_guard = f"{type_col} = %s"
    sql = f'{type_guard} AND {id_col} IN (SELECT "id" FROM {target_table} WHERE {sub_where})'
    params: list[Any] = [predicate.type_value, *sub_params]
    return sql, params
```

Add the dispatch case in `_compile_predicate_impl` (after the `ExistsCheck` case, line 1051-1053):

```python
        case PolyPathCheck():
            return _compile_poly_path_check(
                predicate, entity_name, fk_graph, schema=schema, policy=policy
            )
```

Import `PolyPathCheck` and `_inline_sql_literal` if not already in scope (both live in/near this module — `_inline_sql_literal` is at rls/predicate_compiler ~line 115; `PolyPathCheck` from `dazzle.core.ir.predicates`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_poly_ref_compile.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/http/runtime/predicate_compiler.py tests/unit/test_poly_ref_compile.py
git add src/dazzle/http/runtime/predicate_compiler.py tests/unit/test_poly_ref_compile.py
git commit -m "feat(compiler): #1448 _compile_poly_path_check (type-guard + uuid IN subquery)"
```

---

### Task 9: RLS policy mode + #1447 degradation coverage

**Files:**
- (Compiler already handles policy mode in Task 8.)
- Test: `tests/unit/test_poly_ref_rls.py` (create)

**Interfaces:**
- Consumes: `compile_predicate_policy`, `build_rls_scope_policy_ddl`.
- Produces: a verified policy-body string for a poly scope, and a verified degradation when the sub isn't policy-expressible (no new production code beyond Task 8 — this task proves the policy path + the #1447 hook).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_poly_ref_rls.py
import pytest

from dazzle.core.ir.predicates import PolyPathCheck, UserAttrCheck, ExistsCheck, ExistsBinding, CompOp
from dazzle.http.runtime.predicate_compiler import compile_predicate_policy


def test_poly_policy_body(simple_fk_graph, entity_types):
    node = PolyPathCheck(
        field="target", type_field="target_type", type_value="Cohort",
        id_field="target_id", target_entity="Cohort",
        sub=UserAttrCheck(field="uploaded_by", op=CompOp.EQ, user_attr="entity_id"),
    )
    body = compile_predicate_policy(node, "AIJob", simple_fk_graph, entity_types=entity_types)
    assert "\"target_type\" = 'Cohort'" in body
    assert "current_setting(" in body                   # GUC read for current_user
    assert "%s" not in body                             # param-free


def test_poly_policy_degrades_when_sub_not_expressible(simple_fk_graph, entity_types):
    # An ExistsCheck with an entity-column binding is NOT policy-expressible
    # (the compiler raises ValueError) → poly wrapping it must propagate that.
    node = PolyPathCheck(
        field="target", type_field="target_type", type_value="Cohort",
        id_field="target_id", target_entity="Cohort",
        sub=ExistsCheck(
            target_entity="Membership",
            bindings=[ExistsBinding(junction_field="cohort_id", target="some_column")],
        ),
    )
    with pytest.raises(ValueError):
        compile_predicate_policy(node, "AIJob", simple_fk_graph, entity_types=entity_types)
```

> Reuse the `entity_types` / `simple_fk_graph` fixtures from `tests/unit/test_rls_scope_policies.py` (grep `compile_predicate_policy(` there).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_poly_ref_rls.py -q`
Expected: FAIL on the first test if Task 8's policy branch is wrong; the degradation test should already pass (ValueError propagates) — confirm both after fixes.

- [ ] **Step 3: Fix any policy-mode gaps in `_compile_poly_path_check`**

If `test_poly_policy_body` fails, verify the policy branch added in Task 8 inlines the literal via `_inline_sql_literal` and recurses with `policy=policy`. No further code if Task 8 is correct — this task is the policy-mode proof + the degradation guarantee.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_poly_ref_rls.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
ruff format tests/unit/test_poly_ref_rls.py src/dazzle/http/runtime/predicate_compiler.py
git add tests/unit/test_poly_ref_rls.py src/dazzle/http/runtime/predicate_compiler.py
git commit -m "test(rls): #1448 poly_ref policy-mode body + #1447 degradation propagation"
```

---

### Task 10: Traceability oracle — `dazzle db explain-scope`

**Files:**
- Modify: `src/dazzle/cli/db.py` (add command next to `explain-aggregate` at line ~1861)
- Test: `tests/unit/test_explain_scope_cli.py` (create)

**Interfaces:**
- Consumes: `load_project_appspec`, `compile_predicate`, `compile_predicate_policy`.
- Produces: `dazzle db explain-scope <Entity> <verb> [--persona P]` printing, per scope rule: the predicate tree, the app-layer WHERE (markers shown symbolically), and the RLS policy body **or** the degradation reason.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_explain_scope_cli.py
from typer.testing import CliRunner

from dazzle.cli.db import db_app  # the Typer app

runner = CliRunner()


def test_explain_scope_prints_compiled_forms(tmp_poly_project):
    # tmp_poly_project: a project dir with an AIJob poly_ref scope (build a tiny
    # fixture or reuse fixtures/scope_runtime once Task 11 adds the entity).
    result = runner.invoke(
        db_app, ["explain-scope", "AIJob", "read"], env={"DAZZLE_PROJECT_ROOT": str(tmp_poly_project)}
    )
    assert result.exit_code == 0
    assert "target_type" in result.stdout
    assert "RLS" in result.stdout or "app-layer" in result.stdout
```

> If `load_project_appspec` reads `Path.cwd()`, use `runner.invoke(..., )` with a chdir context (monkeypatch `Path.cwd`) as the other `db.py` CLI tests do (grep `runner.invoke(db_app` in `tests/unit/test_cli_db*.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_explain_scope_cli.py -q`
Expected: FAIL — no such command.

- [ ] **Step 3: Add the command**

In `src/dazzle/cli/db.py`, mirror `explain_aggregate_command` (line 1861):

```python
@db_app.command(name="explain-scope")
def explain_scope_command(
    entity: str = typer.Argument(..., help="Entity name (e.g. AIJob)"),
    verb: str = typer.Argument(..., help="read | list | create | update | delete"),
    persona: str = typer.Option("", "--persona", "-p", help="Filter to one persona"),
) -> None:
    """Print the compiled scope predicate, app-layer WHERE, and RLS policy (or the
    #1447 degradation reason) for <Entity>.<verb> — the #1448 traceability oracle."""
    from dazzle.http.runtime.predicate_compiler import (
        compile_predicate,
        compile_predicate_policy,
    )
    from dazzle.http.runtime.entity_types import EntityTypeResolver  # confirm import path

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    ent = next((e for e in appspec.domain.entities if e.name == entity), None)
    if ent is None or ent.access is None:
        console.print(f"[red]No scoped entity:[/red] {entity}")
        raise typer.Exit(code=1)

    fk_graph = appspec.fk_graph
    entity_types = EntityTypeResolver.from_appspec(appspec)  # confirm constructor
    rules = [
        r for r in ent.access.scopes
        if (r.operation.value if hasattr(r.operation, "value") else str(r.operation)) == verb
        and (not persona or persona in (getattr(r, "personas", None) or []))
    ]
    if not rules:
        console.print(f"[yellow]No {verb} scope rules on {entity}[/yellow]")
        return

    for rule in rules:
        personas = ", ".join(getattr(rule, "personas", None) or []) or "*"
        console.print(f"\n[bold]{entity}.{verb}[/bold] (as {personas})")
        console.print(f"[dim]predicate:[/dim] {rule.predicate!r}")
        sql, params = compile_predicate(rule.predicate, entity, fk_graph)
        console.print(f"[bold]app-layer WHERE:[/bold] {sql or '(no filter)'}")
        console.print(f"[dim]params:[/dim] {params}")
        try:
            body = compile_predicate_policy(
                rule.predicate, entity, fk_graph, entity_types=entity_types
            )
            console.print(f"[bold]RLS policy:[/bold] {body}")
            console.print("[green]verdict:[/green] RLS")
        except ValueError as exc:
            console.print(f"[yellow]verdict:[/yellow] app-layer (degraded: {exc})")
```

> Confirm `EntityTypeResolver` import path + constructor (grep `EntityTypeResolver` — it's passed to `build_rls_scope_policy_ddl`). If `appspec.fk_graph` may be None on a freshly-loaded spec, build it via `FKGraph.from_entities(appspec.domain.entities)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_explain_scope_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/cli/db.py tests/unit/test_explain_scope_cli.py
git add src/dazzle/cli/db.py tests/unit/test_explain_scope_cli.py
git commit -m "feat(cli): #1448 dazzle db explain-scope traceability oracle"
```

---

### Task 11: Fixture + real-Postgres integration proof

**Files:**
- Modify: `fixtures/scope_runtime/dsl/domain.dsl` (add a poly_ref entity + per-type scope)
- Modify: `tests/integration/test_scope_runtime_pg.py` (add the poly-scope test class)
- Test: the integration test itself (real PG)

**Interfaces:**
- Consumes: everything above.
- Produces: a live proof that a teacher sees only `JobLog` rows whose `subject` is an `Enrolment` in their department, not peers', not `Department`-typed rows; admin (`all`) sees everything within-tenant; the tenant_fence still denies cross-tenant.

- [ ] **Step 1: Add the fixture entity (failing — no table/scope yet)**

In `fixtures/scope_runtime/dsl/domain.dsl`, add (Enrolment already has `teaching_group.department = current_user.department as: teacher`; reuse it as the scoped branch target):

```dsl
entity JobLog "Job Log":
  id: uuid pk
  cost: decimal
  subject: poly_ref [Enrolment, Department]

  permit: read as: teacher
  scope:  read: subject[Enrolment].teaching_group.department = current_user.department  as: teacher

  permit: read as: admin
  scope:  read: all  as: admin
```

- [ ] **Step 2: Write the failing integration test**

In `tests/integration/test_scope_runtime_pg.py`, add a test (mirror the existing Enrolment read tests). Seed via `_sql_insert`:
- a `JobLog` with `subject_type='Enrolment'`, `subject_id=<math enrolment id>` (teacher_math's dept) → teacher_math **sees** it;
- a `JobLog` with `subject_type='Enrolment'`, `subject_id=<science enrolment id>` → teacher_math **does not** see it (out-of-scope subject);
- a `JobLog` with `subject_type='Department'`, `subject_id=<math dept id>` → teacher_math **does not** see it (out-of-scope discriminator).

```python
class TestPolyRefScope:
    @pytest.mark.asyncio
    async def test_teacher_sees_only_in_scope_enrolment_jobs(self, scope_app):
        # seed three JobLog rows (see plan); then:
        client = await scope_app.client_as("teacher_math")
        resp = await client.get("/api/joblog")          # confirm the list route path
        ids = {row["id"] for row in resp.json()["items"]}  # confirm response shape
        assert scope_app.math_job_id in ids
        assert scope_app.science_job_id not in ids
        assert scope_app.dept_job_id not in ids
```

> Confirm the list API path + JSON shape from the existing Enrolment test in the same file. Add the three seeded ids to `_ScopeRuntimeApp.__init__` and `_seed`.

- [ ] **Step 3: Run it to verify it fails, then passes once the stack is wired**

Run (requires PG): `TEST_DATABASE_URL=$DATABASE_URL python -m pytest tests/integration/test_scope_runtime_pg.py::TestPolyRefScope -q`
Expected: FAIL first (no JobLog table / scope), PASS after the fixture + seeds are added and the full stack (Tasks 1-8) is in place.

- [ ] **Step 4: Run the scope_runtime unit + drift tests**

Run: `python -m pytest tests/unit/test_docs_drift.py tests/unit/test_scope_rules.py -q`
Expected: PASS (the new fixture entity must not break docs-drift; if `fixtures/` is drift-gated, update the CLAUDE.md fixtures line — see Task 12).

- [ ] **Step 5: Commit**

```bash
ruff format tests/integration/test_scope_runtime_pg.py
git add fixtures/scope_runtime/dsl/domain.dsl tests/integration/test_scope_runtime_pg.py
git commit -m "test(integration): #1448 real-PG poly_ref scope proof (teacher branch isolation)"
```

---

### Task 12: Docs, grammar, counter-prior, CHANGELOG, drift gates + ship

**Files:**
- Modify: `docs/reference/grammar.md` (scope forms), `.claude/CLAUDE.md` (DSL Quick Reference scope-rules block + fixtures line if needed)
- Modify: `docs/counter-priors/polymorphic-associations*.md` (cross-link the safe construct)
- Modify: `CHANGELOG.md` (Added + Agent Guidance)
- Modify: `tests/unit/test_docs_drift.py` expectations if the scope-forms list is gated

- [ ] **Step 1: Update grammar + quick reference**

Add the `poly_ref` field type and the `target[Type].path` scope form to `docs/reference/grammar.md` and the **Scope rules** block in `.claude/CLAUDE.md` (the bulleted list of supported forms), e.g.:

```
- Polymorphic ref: `subject[Enrolment].teaching_group.department = current_user.department` — a typed `poly_ref subject [Enrolment, Department]` field; `[Type]` selects the branch, then a normal path. Bare `subject.x` (no selector) is a validation error.
```

- [ ] **Step 2: Cross-link the counter-prior**

In `docs/counter-priors/polymorphic-associations*.md`, add a "Safe construct" note pointing at `poly_ref` + `dazzle db explain-scope`.

- [ ] **Step 3: CHANGELOG (Added + Agent Guidance + non-goals)**

Under `## [Unreleased]` → `### Added`:

```
- **#1448 `poly_ref` polymorphic-ref scoping primitive.** `poly_ref name [T1, T2]` (two columns `name_type text` + `name_id uuid`, targets uuid-pk) + the `name[Type].path` scope selector compile to a type-guarded uuid subquery in both app-layer and RLS modes (degrades via #1447 when the sub-predicate isn't RLS-expressible). New `dazzle db explain-scope <Entity> <verb>` traceability oracle. Non-goals: create-scope poly probe (gateway creates as admin), nullable poly_ref, non-uuid-pk targets, poly_ref on subtype tables, framework-AIJob adoption (needs app-derived dynamic target sets — follow-on).
```

Add `### Agent Guidance`:

```
- Reach for `poly_ref` instead of raw `entity_type`/`entity_id` when an entity references one of several target types. Scope it with `field[TargetType].path`; a bare `field.x` is a validation error. Verify any poly scope with `dazzle db explain-scope <Entity> <verb>` — it prints the app-layer WHERE + the RLS policy (or the degrade reason).
```

- [ ] **Step 4: Run the full gate**

```bash
python -m pytest tests/unit/ -q -m "not e2e" -p no:cacheprovider
uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/
uv run mypy src/dazzle
uv run lint-imports
python -m pytest tests/unit/test_docs_drift.py -q
```
Expected: all green. Fix any drift (the MCP-tools / scope-forms / fixtures lists are drift-gated).

- [ ] **Step 5: Ship**

```bash
# /bump patch, then:
git add -A
ruff format $(git diff --name-only -- '*.py')
git commit -m "feat: #1448 poly_ref polymorphic-ref scoping primitive + explain-scope oracle"
git tag vX.Y.Z   # the bumped version
git push --follow-tags
# comment on #1448 summarising; close it (primitive shipped; framework-AIJob adoption tracked as follow-on)
```

---

## Self-Review

**Spec coverage:**
- §3 storage (uuid id, no cast) → Task 4. §4 surface (`target[Type].path`, selector-required, multi-branch via repeated rules) → Tasks 5/6/7. §5 IR+parser → Tasks 1/2/3/5/6. §6 app compiler → Task 8. §7 RLS+degradation → Tasks 8/9. §8 FK-graph/validation → Task 7 (note: branch-edge resolution is handled in the predicate builder + validator rather than mutating `FKGraph` internals — the sub validates via the existing `resolve_path`/`field_exists` rooted on the target, which covers the spec's intent without a new edge type; if a future multi-hop poly sub needs graph-level branch edges, that's an additive follow-on). §9 oracle → Task 10. §10 AIJob → **deferred to follow-on** (framework entity, app-derived targets) — explicitly logged in Task 12 CHANGELOG non-goals (no silent cap). §11 tests → Tasks 9/11. §12 non-goals → Task 12. §13 rubric → satisfied by the oracle (Task 10) + validation (Task 7) + PG proof (Task 11).
- **Gap surfaced + resolved:** the spec implied `FKGraph` gains conditional edges (§8); the plan instead resolves the branch in the predicate builder/validator (simpler, no IR-graph mutation) and notes the graph-edge version as a follow-on only if multi-hop poly subs need it. The Task-11 fixture uses a depth-2 sub (`subject[Enrolment].teaching_group.department`) which exercises exactly that multi-hop case through the existing `resolve_path` rooted on the target — so it is covered.

**Placeholder scan:** every code step shows real code. The only `> Note:` callouts are *confirm-the-exact-local-shape* instructions (constructor kwargs, import paths, route paths) that depend on sibling test conventions — each names the exact grep to run. No "TBD"/"add error handling"/"similar to Task N".

**Type consistency:** `PolyPathCheck` field names (`field`, `type_field`, `type_value`, `id_field`, `target_entity`, `sub`) are identical across Tasks 1/6/7/8/10. Compiler returns `tuple[str, list[Any]]` (param) / `str` (policy) consistently. `poly_targets` used identically in Tasks 1/3/4/7.

**Scope:** one primitive, one issue, fully in-repo + testable; AIJob real adoption correctly carved out as a follow-on.
