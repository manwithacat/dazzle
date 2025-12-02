# Contact Manager

> **Complexity**: Beginner+ | **Entities**: 1 | **DSL Lines**: ~55

A personal contact management app demonstrating the **DUAL_PANE_FLOW** archetype with master-detail interface. This example builds on `simple_task` by introducing signal weighting and layout archetypes.

## Quick Start

```bash
cd examples/contact_manager
dazzle dnr serve
```

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

## What This Example Demonstrates

### DSL Features

| Feature | Usage |
|---------|-------|
| **Email Field Type** | `email: email unique required` with validation |
| **Indexes** | Multi-column index: `index last_name,first_name` |
| **Workspace Signals** | List + detail dual-signal pattern |
| **Display Mode** | `display: detail` creates DETAIL_VIEW signal |
| **Archetype Selection** | DUAL_PANE_FLOW from signal weighting |

### Building on simple_task

This example adds:
1. **Unique constraints** - Email must be unique across contacts
2. **Database indexes** - For efficient alphabetical sorting
3. **Workspace archetypes** - Layout determined by signal weights
4. **Signal weighting** - `display: detail` adds +0.2 to weight

## The DUAL_PANE_FLOW Archetype

This archetype provides a master-detail interface:

```
┌─────────────────────────────────────────┐
│ Contacts                                │
├──────────────┬──────────────────────────┤
│ Contact List │ Contact Details          │
│              │                          │
│ □ Alice A.   │ Bob Brown                │
│ ■ Bob B.     │ bob@example.com          │
│ □ Carol C.   │ (555) 123-4567           │
│ ...          │                          │
│              │ Company: Acme Corp       │
│              │ Title: Engineer          │
└──────────────┴──────────────────────────┘
```

### Archetype Selection

The archetype is automatically selected based on signal weights:

| Signal | Type | Weight | Calculation |
|--------|------|--------|-------------|
| `contact_list` | ITEM_LIST | 0.6 | base 0.5 + limit 0.1 |
| `contact_detail` | DETAIL_VIEW | 0.7 | base 0.5 + detail 0.2 |

**Criteria for DUAL_PANE_FLOW**:
- List weight ≥ 0.3 (0.6 ✓)
- Detail weight ≥ 0.3 (0.7 ✓)

## Project Structure

```
contact_manager/
├── SPEC.md              # Product specification
├── README.md            # This file
├── dazzle.toml          # Project configuration
└── dsl/
    └── app.dsl          # DAZZLE DSL definition
```

## Key DSL Patterns

### Email with Unique Constraint
```dsl
entity Contact "Contact":
  email: email unique required
  # email field type provides validation
  # unique constraint prevents duplicates
```

### Multi-Column Index
```dsl
entity Contact "Contact":
  ...
  index last_name,first_name
  # Optimizes ORDER BY last_name, first_name
```

### Dual-Signal Workspace
```dsl
workspace contacts "Contacts":
  contact_list:
    source: Contact
    limit: 20
    # Creates ITEM_LIST signal (weight 0.6)

  contact_detail:
    source: Contact
    display: detail
    # Creates DETAIL_VIEW signal (weight 0.7)
```

## User Stories

| ID | Story | Description |
|----|-------|-------------|
| US-1 | Browse Contact List | Scroll and search contacts |
| US-2 | View Contact Details | See full info in detail pane |
| US-3 | Create New Contact | Add with required email |
| US-4 | Edit Contact | Update any field |
| US-5 | Favorite Contacts | Star important contacts |

## Running Tests

```bash
# Validate DSL
dazzle validate

# Run API tests
dazzle dnr test
```

## Learning Path

**Previous**: `simple_task` (Beginner) - Entity basics, CRUD surfaces

**Next**: `support_tickets` (Intermediate) - Entity relationships, refs

## Key Learnings

1. **`display: detail` is essential** for DUAL_PANE_FLOW
   - Without it, different archetype selected

2. **Signal weights drive layout**
   - Each signal type has base weight
   - Modifiers like `limit`, `display` adjust weight
   - Archetype selected based on weight thresholds

3. **Indexes improve performance**
   - Multi-column indexes for sorting
   - Unique indexes for constraints

## Customization Ideas

Try modifying this example:

1. Add a `category` enum (personal, work, family)
2. Create a favorites-only workspace region
3. Add an attention signal for contacts without phone numbers
4. Change to SCANNER_TABLE by removing `contact_detail`

## Screenshots

### List View
![List View](screenshots/list_view.png)

### Create Form
![Create Form](screenshots/create_form.png)

---

*Part of the DAZZLE Examples collection. See `/examples/README.md` for the full learning path.*
