# DSL Anti-Pattern Guidance in MCP Output

> **For agentic workers:** Use superpowers:writing-plans to create an implementation plan from this spec.

**Goal:** Add modeling anti-pattern detection and guidance across three MCP surfaces so agents naturally avoid common mistakes when generating or modifying DSL.

**Motivation:** Users are refactoring away from polymorphic keys toward proper entity modeling — a sign the DSL works well. The inference KB currently *recommends* the polymorphic pattern. Fix that and add broader guidance.

---

## The Five Anti-Patterns

### 1. Polymorphic Keys

**Anti-pattern:** `item_type: enum[post,photo] + item_id: uuid` instead of typed `ref` fields.

**Why it's wrong:** Breaks referential integrity, prevents the parser's linker from validating relationships, and blocks runtime auto-include of related data.

**Prefer:** Separate typed refs. If a Comment can belong to a Post or Photo, use two nullable refs:

```dsl
# Bad
commentable_type: enum[post,photo] required
commentable_id: uuid required

# Good
post: ref Post        # nullable — set when comment is on a post
photo: ref Photo      # nullable — set when comment is on a photo
```

For true many-to-many, use a junction entity.

### 2. God Entities

**Anti-pattern:** Single entity with 15+ fields spanning unrelated concerns (e.g., Order with address fields, line items, payment details, delivery tracking all inline).

**Why it's wrong:** Makes surfaces unwieldy, RBAC rules overly broad, and state machines complex. The DSL's entity + ref model is designed for decomposition.

**Prefer:** Separate entities connected by refs:

```dsl
# Bad: 25-field Order entity with address, payment, delivery inline

# Good
entity Order "Order":
  customer: ref Customer required
  shipping_address: ref Address
  status: enum[draft,placed,shipped,delivered]=draft

entity OrderLine "Order Line":
  order: ref Order required
  product: ref Product required
  quantity: int required

entity Payment "Payment":
  order: ref Order required
  amount: decimal(10,2) required
  method: enum[card,bank,cash]
```

### 3. Soft-Delete Booleans

**Anti-pattern:** `is_deleted: bool`, `deleted_at: datetime`, or `archived_at: datetime` as a field instead of using the DSL's state machine.

**Why it's wrong:** Creates invisible data that scope rules must manually filter, breaks list counts, and bypasses the transitions block which provides audit trails and role-gated deletion.

**Prefer:** State machine transition to a terminal state, or simply delete the record:

```dsl
# Bad
is_deleted: bool=false
deleted_at: datetime

# Good — use a state machine
status: enum[active,archived]=active

transitions:
  active -> archived: role(admin)
```

### 4. Stringly-Typed Refs

**Anti-pattern:** `customer_email: str` or `assigned_user_name: str` used as a reference to another entity instead of a proper `ref` field.

**Why it's wrong:** Loses relational semantics. The runtime can't auto-include the related record, FK enforcement is absent, and scope rules like `current_user.school` can't traverse the relationship.

**Prefer:** Typed refs:

```dsl
# Bad
customer_email: str(200) required
assigned_user_name: str(100)

# Good
customer: ref Customer required
assigned_to: ref User
```

### 5. Duplicated Fields

**Anti-pattern:** Copying parent entity fields into child entities (e.g., `school_name: str` on StudentProfile when `school: ref School` already exists).

**Why it's wrong:** Creates data inconsistency when the parent changes. The runtime auto-includes ref data in API responses and the UI resolves display names through the relation.

**Prefer:** Use the ref and let the runtime resolve:

```dsl
# Bad
entity StudentProfile "Student":
  school: ref School required
  school_name: str(200)       # duplicates School.name
  school_address: str(500)    # duplicates School.address

# Good — school: ref School is sufficient
# The runtime auto-includes School.name in API responses
entity StudentProfile "Student":
  school: ref School required
```

---

## Integration Points

### 1. Inference KB (`inference_kb.toml`)

**Remove** the existing `polymorphic_owner` relationship pattern entry. **Add** a new `[[modeling_guidance]]` section with 5 entries.

Each TOML entry has:

```toml
[[modeling_guidance]]
id = "no_polymorphic_keys"
name = "Prefer Typed Refs Over Polymorphic Keys"
triggers = ["can belong to X or Y", "owner can be", "polymorphic", "attachable", "commentable", "taggable"]
anti_pattern = "item_type: enum[...] + item_id: uuid"
prefer = "Separate nullable ref fields or a junction entity"
rationale = "Polymorphic keys break referential integrity, prevent linker validation, and block runtime auto-include"
example = """..."""
```

### Inference engine changes (`inference.py`)

**`_SUGGESTION_SCHEMA`** — add entry for the new category:

```python
"modeling_guidance": (
    "modeling_guidance",
    {"avoid": "anti_pattern", "prefer": "prefer", "why": "rationale"},
    {"example": "example"},
),
```

This ensures `_inference_entity_to_suggestion` builds a suggestion dict with `avoid` and `prefer` keys when a `modeling_guidance` entry matches.

**`trigger_key_map`** in `list_all_patterns()` — add:

```python
"modeling_guidance": "modeling_guidance_triggers",
```

So browsing agents can see what vocabulary activates anti-pattern guidance.

**`_GUIDANCE`** — append anti-pattern summary:

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

### KG seeder changes (`seed.py`)

**`categories` list** — add:

```python
("modeling_guidance", "triggers"),
```

**`SEED_SCHEMA_VERSION`** — bump from `2` to `3`. Without this, existing deployments won't re-seed and agents will never see the new entries.

### 2. Lint Warnings (`validator.py`)

Add `_lint_modeling_anti_patterns(appspec)` to the `extended_lint()` dispatch list. Use a named constant `_GOD_ENTITY_FIELD_THRESHOLD = 15` at the top of the function.

| Check | Detection Heuristic | Warning Message |
|-------|---------------------|-----------------|
| Polymorphic pairs | For each field named `*_type` with `kind == FieldTypeKind.ENUM`, check if a sibling field `<prefix>_id` with `kind == FieldTypeKind.SCALAR` and `scalar_type == ScalarType.UUID` exists. Extract prefix via `field.name.removesuffix("_type")`. | `Entity '{name}': fields '{prefix}_type' + '{prefix}_id' look like a polymorphic key. Prefer separate ref fields for each target entity.` |
| God entities | Count fields where `kind != FieldTypeKind.COMPUTED` and `name not in ("id", "created_at", "updated_at")`. Warn if count > `_GOD_ENTITY_FIELD_THRESHOLD`. | `Entity '{name}' has {n} fields — consider decomposing into smaller entities connected by refs.` |
| Soft-delete flags | Field named `is_deleted`, `deleted`, `deleted_at`, or `archived_at` on an entity that has no `transitions` block. | `Entity '{name}': field '{field}' is a soft-delete flag. Prefer a state machine with a terminal state (e.g., 'archived').` |
| Stringly-typed refs | Field named `<entity_name>_name` or `<entity_name>_email` where `<entity_name>` matches a known entity (case-insensitive) **and the field is not on the entity named `<entity_name>` itself**. Build entity name set once from `appspec.domain.entities`. | `Entity '{name}': field '{field}' looks like a string copy of {target}.{attr}. Use 'ref {target}' instead — the runtime auto-includes related data.` |
| Duplicated ref fields | Entity has a `ref X` field. Look up entity `X` in `appspec.domain.entities`. If found, check for sibling fields named `<x_lower>_<field>` where `<field>` is a field name on entity X. **Skip check silently if ref target entity not found.** | `Entity '{name}': field '{field}' may duplicate {target}.{attr} — the ref already provides access via auto-include.` |

All emit **warnings**, never errors.

### 3. Inference `_guidance` String

See updated `_GUIDANCE` constant above in the inference engine changes section.

---

## Files to Modify

| File | Change |
|------|--------|
| `src/dazzle/mcp/inference_kb.toml` | Remove `polymorphic_owner`, add 5 `[[modeling_guidance]]` entries |
| `src/dazzle/mcp/inference.py` | Update `_GUIDANCE`, add `modeling_guidance` to `_SUGGESTION_SCHEMA` and `trigger_key_map` |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Add `("modeling_guidance", "triggers")` to categories, bump `SEED_SCHEMA_VERSION` to 3 |
| `src/dazzle/core/validator.py` | Add `_lint_modeling_anti_patterns()`, wire into `extended_lint()` |
| `tests/unit/test_lint_anti_patterns.py` | New — tests for each lint heuristic (construct entities with `FieldSpec`/`FieldType` IR objects) |
| `tests/unit/test_inference_guidance.py` | New — tests for inference KB anti-pattern entries |

## Implementation Notes

- Lint tests must construct IR entities using `FieldSpec(name=..., type=FieldType(kind=..., ...))` — the IR uses frozen Pydantic models, so use dict-style construction or `model_construct()`.
- The `FieldTypeKind` enum and `ScalarType` enum from `dazzle.core.ir` are needed for polymorphic pair detection.
- The duplicated-ref-fields check requires looking up the ref target entity in `appspec.domain.entities` by name. When the target isn't found (e.g., entity from an unresolved import), skip the check silently.

## What This Does NOT Do

- No hard errors — all guidance is warnings
- No parser/IR changes — purely advisory
- No runtime checks — design-time only
- No changes to existing valid relationship patterns
- No changes to `ref` type behavior
