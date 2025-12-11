# Migration Guide: v0.6 to v0.7

This guide covers migrating DAZZLE projects from v0.6.x to v0.7.x.

## Overview

v0.7 introduces **Business Logic Extraction** features that allow you to express more domain logic directly in DSL, reducing the need for custom code. All changes are **additive and backward compatible** - existing v0.6 projects will work without modification.

## New Features

### 1. State Machines (v0.7.0)

Define entity lifecycle transitions directly in DSL:

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[open, assigned, resolved, closed]
  assignee: ref User

  transitions:
    open -> assigned: requires assignee
    assigned -> resolved: requires resolution_note
    resolved -> closed: auto after 7 days
    * -> open: role(admin)  # reopen from any state
```

**Migration**: Add `transitions:` block to entities with status/state fields.

### 2. Computed Fields (v0.7.0)

Derive values from other fields using aggregate functions:

```dsl
entity Order "Customer Order":
  id: uuid pk
  line_items: has_many LineItem
  subtotal: computed sum(line_items.amount)
  tax: computed subtotal * 0.08
  total: computed subtotal + tax
```

**Migration**: Replace service-based calculations with `computed` fields where appropriate.

### 3. Entity Invariants (v0.7.0)

Express data integrity rules:

```dsl
entity Booking "Room Booking":
  start_date: datetime required
  end_date: datetime required

  invariant: end_date > start_date
    message: "Check-out must be after check-in"
    code: INVALID_DATE_RANGE

  invariant: duration <= 14 days
    message: "Maximum booking duration is 14 days"
```

**Migration**: Move validation logic from services to `invariant:` declarations.

### 4. Intent Declarations (v0.7.1)

Document semantic purpose for LLM understanding:

```dsl
entity Invoice "Invoice":
  intent: "Track customer purchases through billing and payment lifecycle"

  # fields...
```

**Migration**: Add `intent:` to entities to improve LLM-assisted development.

### 5. Domain and Patterns (v0.7.1)

Tag entities with domain hints and common patterns:

```dsl
entity Invoice "Invoice":
  domain: financial
  patterns: audit_trail, lifecycle, soft_delete

  # fields...
```

**Migration**: Add `domain:` and `patterns:` for better semantic indexing.

### 6. Archetypes (v0.7.1)

Define reusable field sets:

```dsl
archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable:
  extends: Timestamped
  created_by: ref User
  updated_by: ref User

entity Invoice "Invoice":
  extends: Auditable

  # Invoice-specific fields...
```

**Migration**: Extract common fields into archetypes using `extends:`.

### 7. Relationship Semantics (v0.7.1)

Express relationship types and delete behaviors:

```dsl
entity Order "Customer Order":
  customer: ref Customer required          # Simple reference
  items: has_many OrderItem cascade        # Owned, delete together
  shipping_address: embeds Address         # Embedded value object

entity OrderItem "Order Line Item":
  order: belongs_to Order                  # Inverse relationship
```

**Delete behaviors:**
- `cascade` - Delete related records
- `restrict` - Prevent deletion if related records exist
- `nullify` - Set foreign key to null
- `readonly` - Prevent modifications

**Migration**: Replace `ref` with semantic relationship types where appropriate.

### 8. Example Data (v0.7.1)

Provide sample data for testing and documentation:

```dsl
entity Priority "Task Priority":
  level: enum[low, medium, high, critical]
  label: str(50) required
  color: str(7)  # hex color

  examples:
    - {level: low, label: "Nice to have", color: "#22c55e"}
    - {level: medium, label: "Should do", color: "#eab308"}
    - {level: high, label: "Must do", color: "#f97316"}
    - {level: critical, label: "Production down", color: "#ef4444"}
```

**Migration**: Add `examples:` blocks to document expected data shapes.

## Ejection Toolchain (v0.7.2)

v0.7.2 introduces the ability to generate standalone code from DNR applications:

```bash
dazzle eject run              # Generate standalone code
dazzle eject --backend        # Backend only (FastAPI)
dazzle eject --frontend       # Frontend only (React)
dazzle eject --dry-run        # Preview without writing
```

Configure in `dazzle.toml`:

```toml
[ejection]
enabled = true

[ejection.backend]
framework = "fastapi"
models = "pydantic-v2"

[ejection.frontend]
framework = "react"
api_client = "zod-fetch"
```

## Breaking Changes

**None.** All v0.7 features are additive. Existing v0.6 projects work without modification.

## Deprecations

**None.** No features deprecated in v0.7.

## Recommended Migration Steps

1. **Update version**: Change `version` in `pyproject.toml` to `0.7.2`

2. **Add intent declarations**: Start with key entities to improve LLM assistance

3. **Add domain tags**: Tag entities by business domain (billing, inventory, etc.)

4. **Extract archetypes**: Identify repeated field patterns (timestamps, audit fields)

5. **Add state machines**: For entities with status/state fields

6. **Add invariants**: Move validation rules from services to DSL

7. **Update relationships**: Use semantic types (`has_many`, `belongs_to`, etc.)

8. **Run validation**: `dazzle validate` to check for any issues

## Getting Help

- Documentation: `docs/` directory
- Examples: `examples/` directory with updated v0.7 DSL
- Issues: GitHub Issues
