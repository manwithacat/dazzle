# v0.7.1 - LLM Cognition & DSL Generation Enhancement

**Status**: Planned
**Focus**: DSL features that improve LLM comprehension and generation quality
**Design Philosophy**: Make intent explicit, reduce inference burden, provide concrete examples

---

## Executive Summary

This release adds DSL constructs specifically designed to help LLMs:
1. **Understand intent** before generating structure
2. **Apply patterns consistently** through explicit tagging
3. **Validate output** through example data and negative constraints
4. **Compose complex specs** through archetypes and derivation chains

The core insight: LLMs reason better from **purpose → implementation** than from structure alone. These features make semantic intent explicit at every level.

---

## Feature Specification

### 1. Intent Declarations

**Problem**: LLMs must infer entity purpose from field names, which leads to inconsistent generation.

**Solution**: Explicit `intent:` at entity level.

```dsl
entity Order "Order":
  intent: "Track customer purchases through the fulfillment lifecycle from cart to delivery"

  id: uuid pk
  status: enum[cart,pending,paid,shipped,delivered,cancelled]=cart
  # ... LLM can now infer appropriate fields from intent
```

**Syntax**:
```ebnf
entity_block = "entity" IDENTIFIER STRING ":" NEWLINE INDENT
               [intent_stmt]
               field_def+
               [business_logic_blocks]
               DEDENT

intent_stmt = "intent" ":" STRING NEWLINE
```

**IR Extension**:
```python
class EntitySpec(BaseModel):
    intent: str | None = None  # New field
```

**Benefits**:
- LLMs can validate generated fields against stated intent
- Enables "does this field support the intent?" reasoning
- Documents purpose for human readers

---

### 2. Domain Hints / Semantic Tags

**Problem**: LLMs regenerate common patterns inconsistently (audit trails, soft deletes, etc.).

**Solution**: Explicit `domain:` and `patterns:` tags that trigger known patterns.

```dsl
entity Invoice "Invoice":
  domain: financial
  patterns: audit_trail, lifecycle, soft_delete

  id: uuid pk
  amount: decimal(10,2) required
  # LLM/generator knows to add: created_at, updated_at, created_by, deleted_at, status with transitions
```

**Syntax**:
```ebnf
entity_block = "entity" IDENTIFIER STRING ":" NEWLINE INDENT
               [intent_stmt]
               [domain_stmt]
               [patterns_stmt]
               field_def+
               DEDENT

domain_stmt = "domain" ":" IDENTIFIER NEWLINE
patterns_stmt = "patterns" ":" pattern_list NEWLINE
pattern_list = IDENTIFIER ("," IDENTIFIER)*
```

**Known Domains**:
| Domain | Implied Patterns |
|--------|------------------|
| `financial` | audit_trail, decimal precision, immutable records |
| `healthcare` | audit_trail, access logging, PII handling |
| `ecommerce` | lifecycle, inventory, pricing |
| `social` | soft_delete, moderation flags |
| `iot` | timestamps, device refs, metrics |

**Known Patterns**:
| Pattern | Generated Fields/Logic |
|---------|------------------------|
| `audit_trail` | created_at, updated_at, created_by, updated_by |
| `soft_delete` | deleted_at, is_deleted, exclude from queries |
| `lifecycle` | status enum, transitions block |
| `versioned` | version number, previous_version ref |
| `temporal` | valid_from, valid_to, is_current |

**IR Extension**:
```python
class EntitySpec(BaseModel):
    domain: str | None = None
    patterns: list[str] = []
```

---

### 3. Relationship Semantics

**Problem**: Current `ref` is ambiguous about ownership and lifecycle.

**Solution**: Explicit relationship types with behavior semantics.

```dsl
entity Order "Order":
  customer: ref Customer required          # Reference (no ownership)
  items: has_many OrderItem cascade        # Owned collection, delete together
  shipping_address: embeds Address         # Embedded value object
  audit_log: has_many AuditEntry readonly  # Read-only back-reference
```

**Relationship Types**:
| Type | Syntax | Semantics |
|------|--------|-----------|
| `ref` | `ref Entity` | Reference, no ownership |
| `has_many` | `has_many Entity [cascade\|restrict\|nullify]` | One-to-many with delete behavior |
| `has_one` | `has_one Entity [cascade\|restrict]` | One-to-one with delete behavior |
| `embeds` | `embeds Entity` | Embedded value, stored inline |
| `belongs_to` | `belongs_to Entity` | Inverse of has_many/has_one |

**Modifiers**:
- `cascade`: Delete children when parent deleted
- `restrict`: Prevent delete if children exist
- `nullify`: Set FK to null on parent delete
- `readonly`: Cannot modify through this relationship

**Syntax**:
```ebnf
field_type = base_type | ref_type | relationship_type

relationship_type = ("has_many" | "has_one" | "embeds" | "belongs_to")
                    IDENTIFIER
                    [relationship_modifier]

relationship_modifier = "cascade" | "restrict" | "nullify" | "readonly"
```

**IR Extension**:
```python
class RelationshipKind(str, Enum):
    REF = "ref"
    HAS_MANY = "has_many"
    HAS_ONE = "has_one"
    EMBEDS = "embeds"
    BELONGS_TO = "belongs_to"

class DeleteBehavior(str, Enum):
    CASCADE = "cascade"
    RESTRICT = "restrict"
    NULLIFY = "nullify"

class RelationshipSpec(BaseModel):
    kind: RelationshipKind
    target: str
    delete_behavior: DeleteBehavior | None = None
    readonly: bool = False
```

---

### 4. Negative Constraints (Anti-patterns)

**Problem**: LLMs generate valid-looking but logically broken specs (self-references, circular dependencies).

**Solution**: Explicit `deny:` block for anti-patterns.

```dsl
entity User "User":
  id: uuid pk
  manager: ref User

  deny:
    - self_reference(manager)     # user.manager != user
    - circular_ref(manager, 3)    # No A→B→C→A chains deeper than 3
```

```dsl
entity Task "Task":
  parent: ref Task

  deny:
    - orphan_on_delete(parent)    # Children must be reassigned/deleted
    - infinite_nesting(parent)    # Max depth enforced
```

**Built-in Anti-patterns**:
| Anti-pattern | Description |
|--------------|-------------|
| `self_reference(field)` | Field cannot reference same record |
| `circular_ref(field, depth)` | Prevent circular chains beyond depth |
| `orphan_on_delete(field)` | Must handle children on parent delete |
| `infinite_nesting(field)` | Enforce max hierarchy depth |
| `duplicate_transition(from, to)` | No duplicate state transitions |

**Syntax**:
```ebnf
deny_block = "deny" ":" NEWLINE INDENT
             deny_rule+
             DEDENT

deny_rule = "-" IDENTIFIER "(" argument_list ")" NEWLINE
```

**IR Extension**:
```python
class DenyRule(BaseModel):
    rule_type: str
    arguments: list[str]

class EntitySpec(BaseModel):
    deny_rules: list[DenyRule] = []
```

---

### 5. Example Data

**Problem**: LLMs struggle with abstract specs; concrete examples dramatically improve comprehension.

**Solution**: Inline `examples:` block with sample records.

```dsl
entity Priority "Priority":
  id: uuid pk
  level: enum[low,medium,high,critical]=medium
  label: str(50) required
  color: str(7)  # hex color

  examples:
    - {level: low, label: "Nice to have", color: "#22c55e"}
    - {level: medium, label: "Should fix", color: "#eab308"}
    - {level: high, label: "Important", color: "#f97316"}
    - {level: critical, label: "Production down", color: "#ef4444"}
```

**Benefits**:
- LLMs understand field semantics from examples
- Auto-generates seed data for testing
- Documents expected data format
- Validates field constraints against examples

**Syntax**:
```ebnf
examples_block = "examples" ":" NEWLINE INDENT
                 example_record+
                 DEDENT

example_record = "-" "{" field_value_list "}" NEWLINE
field_value_list = field_value ("," field_value)*
field_value = IDENTIFIER ":" literal_value
```

**IR Extension**:
```python
class ExampleRecord(BaseModel):
    values: dict[str, Any]

class EntitySpec(BaseModel):
    examples: list[ExampleRecord] = []
```

---

### 6. Derivation Chains (Extended Computed Fields)

**Problem**: Current `computed` is single-expression; complex derivations need chaining.

**Solution**: Allow computed fields to reference other computed fields with explicit dependency tracking.

```dsl
entity Ticket "Ticket":
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
  sla_hours: int = 24
  created_at: datetime auto_add

  # Derivation chain (order matters)
  deadline: computed created_at + hours(sla_hours)
  is_overdue: computed now() > deadline and status != closed
  urgency: computed case(
    is_overdue and priority = critical -> "p0",
    is_overdue -> "p1",
    priority = critical -> "p2",
    default -> priority
  )
```

**New Functions**:
| Function | Description |
|----------|-------------|
| `hours(n)` | Duration of n hours |
| `days(n)` | Duration of n days |
| `now()` | Current timestamp |
| `case(cond -> val, ...)` | Conditional expression |
| `coalesce(a, b, ...)` | First non-null value |

**Dependency Tracking**:
- Parser builds dependency graph of computed fields
- Validates no circular dependencies
- Orders evaluation by dependency
- IR includes `depends_on` for each computed field

**IR Extension**:
```python
class ComputedFieldSpec(BaseModel):
    name: str
    expression: str
    depends_on: list[str] = []  # Other computed fields this depends on
    return_type: str | None = None  # Inferred or explicit
```

---

### 7. Validation Messages

**Problem**: Invariants lack context; LLMs don't understand the business rule intent.

**Solution**: Optional `message:` and `code:` on invariants.

```dsl
entity Booking "Booking":
  start_date: datetime required
  end_date: datetime required

  invariant: end_date > start_date
    message: "Check-out date must be after check-in date"
    code: INVALID_DATE_RANGE

  invariant: end_date - start_date <= days(30)
    message: "Bookings cannot exceed 30 days"
    code: BOOKING_TOO_LONG
```

**Syntax**:
```ebnf
invariant_stmt = "invariant" ":" expression NEWLINE
                 [invariant_message]
                 [invariant_code]

invariant_message = "message" ":" STRING NEWLINE
invariant_code = "code" ":" IDENTIFIER NEWLINE
```

**IR Extension**:
```python
class InvariantSpec(BaseModel):
    condition: str
    message: str | None = None
    code: str | None = None
```

**Benefits**:
- LLMs understand rule intent from message
- Error codes enable i18n and API contracts
- Generated validation includes user-friendly messages

---

### 8. Archetypes (Template Inheritance)

**Problem**: Common patterns (audit fields, timestamps) repeated across entities.

**Solution**: `archetype` blocks that can be extended.

```dsl
# Define reusable patterns
archetype Auditable:
  created_at: datetime auto_add
  updated_at: datetime auto_update
  created_by: ref User
  updated_by: ref User

archetype SoftDeletable:
  deleted_at: datetime
  deleted_by: ref User
  is_deleted: bool = false

# Apply patterns
entity Invoice "Invoice":
  extends: Auditable, SoftDeletable

  id: uuid pk
  amount: decimal(10,2) required
  status: enum[draft,sent,paid,void]=draft
```

**Syntax**:
```ebnf
archetype_block = "archetype" IDENTIFIER ":" NEWLINE INDENT
                  field_def+
                  [business_logic_blocks]
                  DEDENT

entity_block = "entity" IDENTIFIER STRING ":" NEWLINE INDENT
               [extends_stmt]
               ...
               DEDENT

extends_stmt = "extends" ":" archetype_list NEWLINE
archetype_list = IDENTIFIER ("," IDENTIFIER)*
```

**IR Extension**:
```python
class ArchetypeSpec(BaseModel):
    name: str
    fields: list[FieldSpec]
    transitions: list[TransitionSpec] = []
    invariants: list[InvariantSpec] = []
    access_rules: AccessRulesSpec | None = None

class EntitySpec(BaseModel):
    extends: list[str] = []  # Archetype names
```

**Resolution**:
- Fields from archetypes merged into entity
- Entity fields override archetype fields
- Multiple archetypes applied left-to-right
- Linker validates no conflicts

---

### 9. Scenario Definitions

**Problem**: Business rules are abstract; executable examples clarify intent.

**Solution**: `scenarios:` block with given/when/then structure.

```dsl
entity Ticket "Ticket":
  status: enum[open,assigned,resolved,closed]=open
  assignee: ref User
  resolution: text

  transitions:
    open -> assigned: requires assignee
    assigned -> resolved: requires resolution
    resolved -> closed

  scenarios:
    happy_path:
      given: {status: open, assignee: null}
      when: assign(user_1)
      then: {status: assigned, assignee: user_1}

    resolve_with_note:
      given: {status: assigned, assignee: user_1}
      when: resolve(resolution: "Fixed the bug")
      then: {status: resolved, resolution: "Fixed the bug"}

    blocked_transition:
      given: {status: open, assignee: null}
      when: resolve()
      then: error(TRANSITION_REQUIRES_ASSIGNEE)
```

**Syntax**:
```ebnf
scenarios_block = "scenarios" ":" NEWLINE INDENT
                  scenario_def+
                  DEDENT

scenario_def = IDENTIFIER ":" NEWLINE INDENT
               given_clause
               when_clause
               then_clause
               DEDENT

given_clause = "given" ":" record_literal NEWLINE
when_clause = "when" ":" action_call NEWLINE
then_clause = "then" ":" (record_literal | error_expectation) NEWLINE

action_call = IDENTIFIER "(" [argument_list] ")"
error_expectation = "error" "(" IDENTIFIER ")"
```

**IR Extension**:
```python
class ScenarioSpec(BaseModel):
    name: str
    given: dict[str, Any]
    when_action: str
    when_args: dict[str, Any] = {}
    then_state: dict[str, Any] | None = None
    then_error: str | None = None

class EntitySpec(BaseModel):
    scenarios: list[ScenarioSpec] = []
```

**Benefits**:
- Executable documentation
- Auto-generates test cases
- LLMs can validate transitions against scenarios
- Clarifies edge cases

---

### 10. Cross-Entity Rules

**Problem**: Business logic often spans entities; current DSL is entity-centric.

**Solution**: Top-level `rule` blocks for cross-entity logic.

```dsl
rule OrderFulfillment:
  when: Order.status changes to shipped
  then:
    - Inventory.quantity -= Order.items.quantity
    - Notification.create(
        recipient: Order.customer,
        message: "Your order has shipped!"
      )

rule LowStockAlert:
  when: Inventory.quantity < Inventory.reorder_threshold
  then:
    - Alert.create(
        severity: warning,
        message: "Low stock: {Inventory.product.name}"
      )
```

**Syntax**:
```ebnf
rule_block = "rule" IDENTIFIER ":" NEWLINE INDENT
             when_clause
             then_clause
             DEDENT

when_clause = "when" ":" trigger_expression NEWLINE
trigger_expression = entity_ref "." field_ref "changes" "to" value
                   | entity_ref "." field_ref comparison_op value
                   | entity_ref "created"
                   | entity_ref "deleted"

then_clause = "then" ":" NEWLINE INDENT
              action_stmt+
              DEDENT

action_stmt = "-" (assignment | method_call) NEWLINE
```

**IR Extension**:
```python
class TriggerType(str, Enum):
    FIELD_CHANGE = "field_change"
    FIELD_CONDITION = "field_condition"
    ENTITY_CREATED = "entity_created"
    ENTITY_DELETED = "entity_deleted"

class RuleTrigger(BaseModel):
    type: TriggerType
    entity: str
    field: str | None = None
    condition: str | None = None
    value: Any | None = None

class RuleAction(BaseModel):
    target: str  # Entity.field or Entity.method
    operation: str  # assign, increment, decrement, call
    value: Any | None = None
    arguments: dict[str, Any] = {}

class RuleSpec(BaseModel):
    name: str
    trigger: RuleTrigger
    actions: list[RuleAction]

class AppSpec(BaseModel):
    rules: list[RuleSpec] = []
```

---

## Implementation Priority

| Feature | Effort | LLM Impact | Priority |
|---------|--------|------------|----------|
| `intent:` on entities | Low | High | P0 |
| `examples:` block | Medium | High | P0 |
| `message:` on invariants | Low | Medium | P0 |
| `domain:` / `patterns:` tags | Low | Medium | P1 |
| `extends:` archetypes | Medium | High | P1 |
| Relationship semantics | Medium | Medium | P1 |
| `deny:` anti-patterns | Medium | High | P2 |
| `scenarios:` block | Medium | High | P2 |
| Derivation chains | Medium | Medium | P2 |
| Cross-entity `rule` blocks | High | Medium | P3 |

---

## MCP Server Integration

All new features should be reflected in the semantic index:

```python
# semantics.py additions
"intent": {
    "category": "LLM Cognition (v0.7.1)",
    "definition": "Explicit statement of entity purpose to guide LLM reasoning",
    "syntax": 'intent: "Track customer purchases through fulfillment"',
    "example": "...",
    "best_practices": [
        "State the business goal, not the technical structure",
        "Include lifecycle if the entity has states",
        "Mention key relationships"
    ]
}
```

New MCP tools:
- `lookup_concept("intent")` - Returns intent syntax/examples
- `lookup_concept("archetype")` - Returns archetype patterns
- `find_examples(features=["scenarios"])` - Find projects with scenarios

---

## Success Criteria

1. **Measurable Improvement**: LLM-generated DSL quality improves by observable margin
2. **Parser Complete**: All P0/P1 features parse without errors
3. **IR Complete**: All features represented in IR with full type coverage
4. **Examples Updated**: All example projects use new features appropriately
5. **MCP Updated**: Semantic index includes all new concepts with examples
6. **Tests**: 50+ new unit tests covering new syntax
7. **Backward Compatible**: Existing DSL files parse without modification

---

## Migration Notes

All features are **additive**. Existing DSL files remain valid. New features are optional enhancements.

Recommended adoption order:
1. Add `intent:` to entities (immediate benefit, zero risk)
2. Add `examples:` to enum-heavy entities
3. Add `message:` to existing invariants
4. Introduce archetypes for common patterns
5. Adopt relationship semantics in new entities

---

**Document Owner**: Claude + James
**Created**: 2025-12-10
**Target Release**: v0.7.1
