# Business Logic Extraction: Design Intent

## Overview

DAZZLE's DSL serves as a **compression boundary** (or "chokepoint") between high-value semantic reasoning and low-cost mechanical transformation. The goal is to apply LLM reasoning where it provides the most value—understanding founder intent—while using deterministic code generation for everything that can be derived mechanically.

## The Compression Boundary

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   Founder's Vision                                              │
│   (natural language, implicit assumptions, domain knowledge)    │
│                                                                  │
│                          │                                       │
│                          │ LLM: semantic extraction              │
│                          │ (HIGH TOKEN VALUE)                    │
│                          ▼                                       │
│   ════════════════════════════════════════════════════════════  │
│                     DSL SPECIFICATION                            │
│            (structured, validated, unambiguous)                  │
│   ════════════════════════════════════════════════════════════  │
│                          │                                       │
│                          │ Deterministic: parser + compiler      │
│                          │ (ZERO TOKEN COST)                     │
│                          ▼                                       │
│                                                                  │
│   Generated Artifacts                                           │
│   (API routes, schemas, validation, stubs)                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

The DSL is the chokepoint. Everything above it benefits from LLM reasoning. Everything below it is mechanical.

## Token Value Distribution

| Activity | Token Value | Rationale |
|----------|-------------|-----------|
| Natural language → DSL | **HIGH** | Semantic understanding, disambiguation, domain modeling |
| DSL validation & consistency | **MEDIUM** | Pattern matching, edge case detection |
| DSL → Code generation | **NONE** | Deterministic transformation |
| Generated stub review | **MEDIUM** | Verify generated code matches intent |
| Custom business logic | **HIGH** | Where DSL expressiveness ends |

## Design Principles

### 1. Declarative Over Imperative

Business rules should describe **what** not **how**. This enables:
- Static analysis at parse time
- Multiple output targets (Python, TypeScript, documentation)
- Optimization without changing semantics

```dsl
# Good: declarative constraint
entity Booking:
  invariant: end_date > start_date

# Avoid: imperative logic embedded in DSL
entity Booking:
  on_save: |
    if self.end_date <= self.start_date:
      raise ValidationError("...")
```

### 2. Bounded Expressiveness

The DSL is intentionally **not** Turing-complete. This constraint:
- Guarantees termination of all validations
- Enables exhaustive analysis of state spaces
- Prevents "DSL escape" where complexity hides in rule definitions

### 3. Composable Primitives

Rules should compose from a small set of primitives:
- Field references (`ticket.status`, `order.total`)
- Comparisons (`>`, `<`, `==`, `in`)
- Logical operators (`and`, `or`, `not`)
- Temporal operators (`after`, `within`, `before`)
- Aggregations (`sum`, `count`, `any`, `all`)

Complex rules emerge from composition, not new syntax.

### 4. Escape Hatches are Explicit

When DSL expressiveness is insufficient, the escape to custom code should be:
- Clearly marked in the DSL
- Generate a stub with typed signature
- Document what the custom code is expected to do

```dsl
entity Order:
  # DSL handles the common case
  total: computed sum(line_items.amount)

  # Escape hatch for complex logic
  shipping_cost: custom "Calculate shipping based on weight, destination, and carrier rules"
```

## Rule Categories

### Layer 1: Data Shape (Current)
Entities, fields, types, relationships. Generates API structure.

### Layer 2: Field Constraints
Per-field validation beyond type checking.
```dsl
field email: str unique format(email)
field age: int range(0, 150)
field code: str pattern("[A-Z]{3}-[0-9]{4}")
```

### Layer 3: Entity Invariants
Cross-field constraints that must always hold.
```dsl
entity Booking:
  start_date: datetime
  end_date: datetime

  invariant: end_date > start_date
  invariant: duration <= 14 days
```

### Layer 4: State Machines
Valid state transitions with optional guards.
```dsl
entity Ticket:
  status: enum(open, assigned, resolved, closed)

  transitions:
    open -> assigned: requires assignee
    assigned -> resolved: requires resolution_note
    resolved -> closed: auto after 7 days OR manual
    * -> open: role(admin)  # reopen from any state
```

### Layer 5: Access Rules
Who can see/modify what.
```dsl
entity Document:
  owner: ref User

  access:
    read: owner OR owner.team OR role(admin)
    write: owner OR role(admin)
    delete: role(admin) AND status != "published"
```

### Layer 6: Triggers / Side Effects
Actions that occur in response to state changes.
```dsl
entity Subscription:
  on status -> cancelled:
    emit event(subscription.cancelled)
    schedule send_cancellation_email after 1 hour
```

## Implementation Strategy

### Phase 1: State Machines
- Highest ROI: captures real business logic
- Well-understood pattern with clear semantics
- Directly generates guard code in service layer

### Phase 2: Computed Fields
- Eliminates derived data bugs
- Straightforward expression evaluation
- Can optimize (eager vs lazy, cached vs computed)

### Phase 3: Invariants
- Natural extension of field constraints
- Validates at entity level, not just field level

### Phase 4: Access Rules
- More complex but solves authorization consistently
- Generates middleware/decorators

### Phase 5: Triggers
- Requires event infrastructure
- Deferred until event system is designed

## Stub Expansion

Generated stubs should include:

1. **Type-safe method signatures** from DSL
2. **Validation guards** from constraints/invariants
3. **Transition checks** from state machines
4. **TODO markers** for custom logic escape hatches
5. **Docstrings** explaining what each hook should do

Example output:
```python
class TicketService(BaseService[Ticket]):
    """Auto-generated service for Ticket entity."""

    # From state machine definition
    TRANSITIONS = {
        "open": {"assigned"},
        "assigned": {"resolved", "open"},
        "resolved": {"closed"},
    }

    def update(self, id: str, data: TicketUpdate) -> Ticket:
        current = self.get(id)

        if "status" in data.model_fields_set:
            self._validate_transition(current.status, data.status)

        return super().update(id, data)

    def _validate_transition(self, from_status: str, to_status: str) -> None:
        """Validate state transition is allowed."""
        allowed = self.TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {from_status} to {to_status}"
            )

        # Guard: assigned requires assignee
        if to_status == "assigned":
            self._guard_requires_assignee()

    def _guard_requires_assignee(self) -> None:
        """
        TODO: Implement guard logic.

        DSL specifies: requires assignee
        This should verify the ticket has an assignee before allowing transition.
        """
        raise NotImplementedError("Guard 'requires_assignee' not implemented")
```

## Open Questions

1. **Rule inheritance**: Should entities inherit rules from a base? How do overrides work?

2. **Rule composition**: Can rules reference other rules? `invariant: valid_dates AND valid_capacity`

3. **Temporal rules**: How to express "within 24 hours" or "before end of month"?

4. **Testing rules**: How to generate test cases that exercise rule boundaries?

5. **Rule versioning**: When rules change, how to handle existing data that violates new rules?

## Success Criteria

The design succeeds if:

1. **80% of business logic** can be expressed in DSL without escape hatches
2. **Generated code is readable** - a developer can understand it without DSL knowledge
3. **Rules are testable** - can generate property-based tests from rule definitions
4. **Escape hatches are rare** - custom code is the exception, not the norm
5. **Token cost is front-loaded** - pay once for spec, free transformation thereafter
