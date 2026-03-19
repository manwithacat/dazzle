# Anti-Pattern Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add modeling anti-pattern detection and guidance across inference KB, lint, and inference response output so agents avoid polymorphic keys, god entities, soft-delete booleans, stringly-typed refs, and duplicated fields.

**Architecture:** Replace one TOML entry and add five new `[[modeling_guidance]]` entries in the inference KB. Wire them through the KG seeder and inference engine. Add a `_lint_modeling_anti_patterns` function to the validator. All guidance is warnings, never errors.

**Tech Stack:** Python 3.12, TOML knowledge base, Pydantic IR models, pytest

**Spec:** `docs/superpowers/specs/2026-03-19-anti-pattern-guidance-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle/mcp/inference_kb.toml` | Source of truth for inference patterns — remove `polymorphic_owner`, add `[[modeling_guidance]]` section |
| `src/dazzle/mcp/inference.py` | Inference query engine — update `_GUIDANCE`, `_SUGGESTION_SCHEMA`, `trigger_key_map` |
| `src/dazzle/mcp/knowledge_graph/seed.py` | KG seeder — add category, bump version |
| `src/dazzle/core/validator.py` | Lint rules — add `_lint_modeling_anti_patterns()` |
| `tests/unit/test_lint_anti_patterns.py` | **Create** — lint heuristic tests |
| `tests/unit/test_inference_guidance.py` | **Create** — inference KB integration tests |

---

## Task 1: Inference KB TOML Entries

**Files:**
- Modify: `src/dazzle/mcp/inference_kb.toml`

- [ ] **Step 1: Remove the `polymorphic_owner` entry**

In `inference_kb.toml`, delete lines 1785–1799 (the `[[relationship_patterns]]` entry with `id = "polymorphic_owner"`).

- [ ] **Step 2: Add the `[[modeling_guidance]]` section**

Append before the `# SITESPEC SECTION INFERENCE` comment block:

```toml
# =============================================================================
# MODELING GUIDANCE (Anti-Pattern Steering)
# =============================================================================
# Surfaces when agents query with anti-pattern keywords.
# Each entry has anti_pattern (what to avoid) and prefer (what to do instead).

[[modeling_guidance]]
id = "no_polymorphic_keys"
name = "Prefer Typed Refs Over Polymorphic Keys"
triggers = ["can belong to X or Y", "owner can be", "polymorphic", "attachable", "commentable", "taggable", "owner_type", "item_type"]
anti_pattern = "item_type: enum[...] + item_id: uuid"
prefer = "Separate nullable ref fields or a junction entity"
rationale = "Polymorphic keys break referential integrity, prevent linker validation, and block runtime auto-include"
example = """
# BAD — polymorphic key pair
commentable_type: enum[post,photo] required
commentable_id: uuid required

# GOOD — separate typed refs (nullable)
post: ref Post        # set when comment is on a post
photo: ref Photo      # set when comment is on a photo

# GOOD — for many-to-many, use a junction entity
entity ProductTag "Product Tag":
  id: uuid pk
  product: ref Product required
  tag: ref Tag required
"""

[[modeling_guidance]]
id = "no_god_entities"
name = "Decompose God Entities"
triggers = ["too many fields", "large entity", "god entity", "monolith entity", "kitchen sink"]
anti_pattern = "Single entity with 15+ fields spanning unrelated concerns"
prefer = "Separate entities connected by refs"
rationale = "God entities make surfaces unwieldy, RBAC rules overly broad, and state machines complex. The DSL's entity + ref model is designed for decomposition."
example = """
# BAD — 20-field Order with address, payment, delivery inline

# GOOD — decomposed
entity Order "Order":
  customer: ref Customer required
  shipping_address: ref Address
  status: enum[draft,placed,shipped,delivered]=draft

entity OrderLine "Order Line":
  order: ref Order required
  product: ref Product required
  quantity: int required
"""

[[modeling_guidance]]
id = "no_soft_delete"
name = "Use State Machines Instead of Soft-Delete Flags"
triggers = ["soft delete", "is_deleted", "deleted_at", "archived_at", "tombstone", "logical delete"]
anti_pattern = "is_deleted: bool or deleted_at: datetime as a field"
prefer = "State machine transition to a terminal state, or simply delete the record"
rationale = "Soft-delete flags create invisible data that scope rules must manually filter, break list counts, and bypass the transitions block which provides audit trails and role-gated deletion."
example = """
# BAD
is_deleted: bool=false
deleted_at: datetime

# GOOD — state machine
status: enum[active,archived]=active

transitions:
  active -> archived: role(admin)
"""

[[modeling_guidance]]
id = "no_stringly_refs"
name = "Use Typed Refs Instead of String Copies"
triggers = ["customer_email", "user_name as field", "string reference", "denormalized", "copy of name"]
anti_pattern = "customer_email: str or user_name: str used as a reference to another entity"
prefer = "Typed ref fields: customer: ref Customer"
rationale = "String copies lose relational semantics. The runtime can't auto-include the related record, FK enforcement is absent, and scope rules can't traverse the relationship."
example = """
# BAD
customer_email: str(200) required
assigned_user_name: str(100)

# GOOD
customer: ref Customer required
assigned_to: ref User
"""

[[modeling_guidance]]
id = "no_duplicated_fields"
name = "Don't Copy Parent Fields — Use Refs"
triggers = ["duplicated field", "copy parent field", "denormalized name", "school_name on student"]
anti_pattern = "Copying parent entity fields into child entities alongside a ref"
prefer = "Use the ref and let the runtime auto-include related data"
rationale = "Creates data inconsistency when the parent changes. The runtime auto-includes ref data in API responses and the UI resolves display names through the relation."
example = """
# BAD
entity StudentProfile "Student":
  school: ref School required
  school_name: str(200)       # duplicates School.name

# GOOD — ref is sufficient
entity StudentProfile "Student":
  school: ref School required
  # school.name is auto-included in API responses
"""
```

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/mcp/inference_kb.toml
git commit -m "feat: add modeling guidance entries, remove polymorphic_owner"
```

---

## Task 2: KG Seeder + Inference Engine Wiring

**Files:**
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py`
- Modify: `src/dazzle/mcp/inference.py`

- [ ] **Step 1: Write failing test for inference query**

```python
# tests/unit/test_inference_guidance.py
"""Tests for modeling guidance in the inference KB."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


def _import_kg_module(name: str):
    """Import KG module directly to avoid MCP package init issues."""
    path = Path(__file__).parent.parent.parent / "src" / "dazzle" / "mcp" / "knowledge_graph" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"dazzle.mcp.knowledge_graph.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"dazzle.mcp.knowledge_graph.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_store = _import_kg_module("store")
_seed = _import_kg_module("seed")


def _seeded_graph():
    """Create an in-memory KG seeded with framework knowledge."""
    graph = _store.KnowledgeGraph(":memory:")
    _seed.seed_framework_knowledge(graph)
    return graph


class TestModelingGuidanceInference:
    def test_polymorphic_query_returns_guidance(self) -> None:
        from dazzle.mcp.inference import lookup_inference

        graph = _seeded_graph()
        with patch("dazzle.mcp.inference._get_kg", return_value=graph):
            result = lookup_inference("polymorphic")
        suggestions = result.get("suggestions", [])
        guidance = [s for s in suggestions if s.get("type") == "modeling_guidance"]
        assert len(guidance) >= 1
        first = guidance[0]
        assert "avoid" in first
        assert "prefer" in first

    def test_soft_delete_query_returns_guidance(self) -> None:
        from dazzle.mcp.inference import lookup_inference

        graph = _seeded_graph()
        with patch("dazzle.mcp.inference._get_kg", return_value=graph):
            result = lookup_inference("soft delete")
        suggestions = result.get("suggestions", [])
        guidance = [s for s in suggestions if s.get("type") == "modeling_guidance"]
        assert len(guidance) >= 1

    def test_guidance_string_mentions_anti_patterns(self) -> None:
        from dazzle.mcp.inference import _GUIDANCE

        assert "polymorphic" in _GUIDANCE
        assert "god entities" in _GUIDANCE
        assert "soft-delete" in _GUIDANCE

    def test_list_all_includes_modeling_guidance_triggers(self) -> None:
        from dazzle.mcp.inference import list_all_patterns

        graph = _seeded_graph()
        with patch("dazzle.mcp.inference._get_kg", return_value=graph):
            result = list_all_patterns()
        assert "modeling_guidance_triggers" in result
        triggers = result["modeling_guidance_triggers"]
        assert "polymorphic" in triggers
        assert "soft delete" in triggers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_inference_guidance.py -v`
Expected: FAIL — `modeling_guidance` not in `_SUGGESTION_SCHEMA`, KG not seeded with new entries

- [ ] **Step 3: Update `seed.py` — add category and bump version**

In `src/dazzle/mcp/knowledge_graph/seed.py`:

1. Change `SEED_SCHEMA_VERSION = 2` to `SEED_SCHEMA_VERSION = 3`
2. In the `categories` list, add `("modeling_guidance", "triggers")` after `("tool_suggestions", "triggers")`

- [ ] **Step 4: Update `inference.py` — schema, guidance, trigger map**

In `src/dazzle/mcp/inference.py`:

1. Add to `_SUGGESTION_SCHEMA`:

```python
    "modeling_guidance": (
        "modeling_guidance",
        {"avoid": "anti_pattern", "prefer": "prefer", "why": "rationale"},
        {"example": "example"},
    ),
```

2. Replace `_GUIDANCE`:

```python
_GUIDANCE = (
    "These are SUGGESTIONS based on common patterns. "
    "Use your judgment - override when context warrants. "
    "Adapt examples to the specific domain. "
    "Avoid: polymorphic keys (use typed refs), god entities (decompose), "
    "soft-delete booleans (use state machines), stringly-typed refs (use ref), "
    "and duplicated fields (let auto-include resolve)."
)
```

3. Add to `trigger_key_map` in `list_all_patterns()`:

```python
        "modeling_guidance": "modeling_guidance_triggers",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_inference_guidance.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/knowledge_graph/seed.py src/dazzle/mcp/inference.py tests/unit/test_inference_guidance.py
git commit -m "feat: wire modeling_guidance into inference engine and KG seeder"
```

---

## Task 3: Lint — Polymorphic Pair + God Entity Detection

**Files:**
- Modify: `src/dazzle/core/validator.py`
- Create: `tests/unit/test_lint_anti_patterns.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_lint_anti_patterns.py
"""Tests for modeling anti-pattern lint warnings."""

from __future__ import annotations

from dazzle.core import ir


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _make_appspec(entities: list[ir.EntitySpec]) -> ir.AppSpec:
    return ir.AppSpec(
        name="test",
        version="1.0.0",
        domain=ir.DomainSpec(entities=entities),
        surfaces=[],
    )


class TestPolymorphicPairDetection:
    def test_detects_type_plus_id_pair(self) -> None:
        entity = ir.EntitySpec(
            name="Comment",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="commentable_type",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.ENUM,
                        enum_values=["post", "photo"],
                    ),
                ),
                ir.FieldSpec(
                    name="commentable_id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("polymorphic" in w.lower() for w in warnings)

    def test_ignores_unrelated_type_field(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="task_type",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.ENUM,
                        enum_values=["bug", "feature"],
                    ),
                ),
                # No matching task_id field
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert not any("polymorphic" in w.lower() for w in warnings)


class TestGodEntityDetection:
    def test_detects_entity_with_too_many_fields(self) -> None:
        fields = [_id_field()] + [
            ir.FieldSpec(
                name=f"field_{i}",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR),
            )
            for i in range(16)
        ]
        entity = ir.EntitySpec(name="GodEntity", fields=fields)
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("decompos" in w.lower() for w in warnings)

    def test_ignores_normal_entity(self) -> None:
        fields = [_id_field()] + [
            ir.FieldSpec(
                name=f"field_{i}",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR),
            )
            for i in range(5)
        ]
        entity = ir.EntitySpec(name="NormalEntity", fields=fields)
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert not any("decompos" in w.lower() for w in warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_lint_anti_patterns.py -v`
Expected: FAIL — no `polymorphic` or `decompos` warnings

- [ ] **Step 3: Implement polymorphic pair + god entity detection**

In `src/dazzle/core/validator.py`, add before the `extended_lint` function:

```python
_GOD_ENTITY_FIELD_THRESHOLD = 15
_SOFT_DELETE_NAMES = frozenset({"is_deleted", "deleted", "deleted_at", "archived_at"})


def _lint_modeling_anti_patterns(appspec: ir.AppSpec) -> list[str]:
    """Detect common modeling anti-patterns and emit warnings."""
    warnings: list[str] = []
    entity_names = {e.name.lower() for e in appspec.domain.entities}
    entity_map = {e.name: e for e in appspec.domain.entities}

    for entity in appspec.domain.entities:
        field_map = {f.name: f for f in entity.fields}

        # 1. Polymorphic key pairs: *_type (enum) + *_id (uuid)
        for field in entity.fields:
            if field.name.endswith("_type") and field.type.kind == ir.FieldTypeKind.ENUM:
                prefix = field.name.removesuffix("_type")
                sibling_name = f"{prefix}_id"
                sibling = field_map.get(sibling_name)
                if sibling and sibling.type.kind == ir.FieldTypeKind.UUID:
                    warnings.append(
                        f"Entity '{entity.name}': fields '{field.name}' + "
                        f"'{sibling_name}' look like a polymorphic key. "
                        f"Prefer separate ref fields for each target entity."
                    )

        # 2. God entities: too many fields
        meaningful_fields = [
            f
            for f in entity.fields
            if f.name not in ("id", "created_at", "updated_at")
            and ir.FieldModifier.PK not in (f.modifiers or [])
        ]
        if len(meaningful_fields) > _GOD_ENTITY_FIELD_THRESHOLD:
            warnings.append(
                f"Entity '{entity.name}' has {len(meaningful_fields)} fields "
                f"— consider decomposing into smaller entities connected by refs."
            )

    return warnings
```

Then add `warnings.extend(_lint_modeling_anti_patterns(appspec))` to `extended_lint()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_lint_anti_patterns.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/validator.py tests/unit/test_lint_anti_patterns.py
git commit -m "feat(lint): detect polymorphic keys and god entities"
```

---

## Task 4: Lint — Soft-Delete, Stringly-Typed Refs, Duplicated Fields

**Files:**
- Modify: `src/dazzle/core/validator.py`
- Modify: `tests/unit/test_lint_anti_patterns.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_lint_anti_patterns.py`:

```python
class TestSoftDeleteDetection:
    def test_detects_is_deleted_without_state_machine(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="is_deleted",
                    type=ir.FieldType(kind=ir.FieldTypeKind.BOOL),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("soft-delete" in w.lower() for w in warnings)

    def test_detects_deleted_at(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="deleted_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("soft-delete" in w.lower() for w in warnings)

    def test_detects_archived_at(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="archived_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("soft-delete" in w.lower() for w in warnings)

    def test_ignores_when_state_machine_exists(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="deleted_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                ),
            ],
            state_machine=ir.StateMachineSpec(
                status_field="status",
                states=["active", "archived"],
                transitions=[
                    ir.StateTransition(from_state="active", to_state="archived"),
                ],
            ),
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert not any("soft-delete" in w.lower() for w in warnings)


class TestStringlyTypedRefDetection:
    def test_detects_entity_name_field(self) -> None:
        customer = ir.EntitySpec(name="Customer", fields=[_id_field()])
        order = ir.EntitySpec(
            name="Order",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="customer_email",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([customer, order]))
        assert any("string copy" in w.lower() for w in warnings)

    def test_ignores_field_on_own_entity(self) -> None:
        """customer_name on Customer itself is NOT an anti-pattern."""
        customer = ir.EntitySpec(
            name="Customer",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="customer_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([customer]))
        assert not any("string copy" in w.lower() for w in warnings)


class TestDuplicatedRefFieldDetection:
    def test_detects_ref_field_copy(self) -> None:
        school = ir.EntitySpec(
            name="School",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        student = ir.EntitySpec(
            name="Student",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="school",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.REF,
                        ref_entity="School",
                    ),
                ),
                ir.FieldSpec(
                    name="school_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([school, student]))
        assert any("duplicate" in w.lower() for w in warnings)

    def test_ignores_when_ref_target_not_found(self) -> None:
        """If ref target entity doesn't exist, skip check silently."""
        student = ir.EntitySpec(
            name="Student",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="school",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.REF,
                        ref_entity="School",
                    ),
                ),
                ir.FieldSpec(
                    name="school_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        # School entity not in appspec — should not crash
        warnings = extended_lint(_make_appspec([student]))
        assert not any("duplicate" in w.lower() for w in warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_lint_anti_patterns.py -v`
Expected: New tests FAIL — soft-delete/stringly/duplicated checks not implemented

- [ ] **Step 3: Add remaining heuristics to `_lint_modeling_anti_patterns`**

Extend the function in `src/dazzle/core/validator.py` by adding after the god-entity check, still inside the `for entity` loop:

```python
        # 3. Soft-delete flags without state machine
        if entity.state_machine is None:
            for field in entity.fields:
                if field.name in _SOFT_DELETE_NAMES:
                    warnings.append(
                        f"Entity '{entity.name}': field '{field.name}' is a soft-delete "
                        f"flag. Prefer a state machine with a terminal state "
                        f"(e.g., 'archived')."
                    )

        # 4. Stringly-typed refs: <entity>_name or <entity>_email
        for field in entity.fields:
            if field.type.kind not in (ir.FieldTypeKind.STR, ir.FieldTypeKind.EMAIL):
                continue
            for suffix in ("_name", "_email"):
                if field.name.endswith(suffix):
                    prefix = field.name.removesuffix(suffix)
                    if prefix.lower() in entity_names and prefix.lower() != entity.name.lower():
                        target = next(
                            (e.name for e in appspec.domain.entities if e.name.lower() == prefix.lower()),
                            prefix,
                        )
                        warnings.append(
                            f"Entity '{entity.name}': field '{field.name}' looks like "
                            f"a string copy of {target}.{suffix.lstrip('_')}. "
                            f"Use 'ref {target}' instead — the runtime auto-includes related data."
                        )

        # 5. Duplicated ref fields: ref X + x_<field> where <field> exists on X
        for field in entity.fields:
            if field.type.kind != ir.FieldTypeKind.REF or not field.type.ref_entity:
                continue
            target_entity = entity_map.get(field.type.ref_entity)
            if target_entity is None:
                continue  # ref target not found — skip silently
            target_field_names = {f.name for f in target_entity.fields if f.name != "id"}
            ref_lower = field.name.lower()
            for sibling in entity.fields:
                if sibling is field:
                    continue
                if sibling.name.startswith(f"{ref_lower}_"):
                    attr = sibling.name[len(ref_lower) + 1 :]
                    if attr in target_field_names:
                        warnings.append(
                            f"Entity '{entity.name}': field '{sibling.name}' may "
                            f"duplicate {field.type.ref_entity}.{attr} — the ref "
                            f"already provides access via auto-include."
                        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_lint_anti_patterns.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to verify no breakage**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q`
Expected: All pass (existing entities in examples may trigger new warnings but `extended_lint` is only called explicitly, not during normal validation)

- [ ] **Step 6: Lint and type check**

Run: `ruff check src/dazzle/core/validator.py tests/unit/test_lint_anti_patterns.py --fix && ruff format src/dazzle/core/validator.py tests/unit/test_lint_anti_patterns.py`
Run: `mypy src/dazzle/core/validator.py`

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/validator.py tests/unit/test_lint_anti_patterns.py
git commit -m "feat(lint): detect soft-delete flags, stringly-typed refs, duplicated fields"
```

---

## Task 5: Final Verification + Push

**Files:**
- None new — integration check

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q`
Expected: All pass

- [ ] **Step 2: Verify inference KB loads correctly**

```python
python -c "
from dazzle.mcp.inference import lookup_inference, list_all_patterns
r = lookup_inference('polymorphic')
print('Polymorphic query:', [s['type'] for s in r.get('suggestions', [])])
r2 = list_all_patterns()
print('Guidance triggers:', r2.get('modeling_guidance_triggers', [])[:5])
"
```

Expected: `modeling_guidance` type in suggestions, trigger terms listed

- [ ] **Step 3: Verify lint runs without false positives on examples**

Run: `dazzle lint` in each example project directory to verify no unexpected warnings from the new heuristics. If any example entity legitimately triggers a warning (e.g., the shapes_validation example), verify the warning is accurate and helpful.

- [ ] **Step 4: Push**

```bash
git push
```
