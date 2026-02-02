# Support Ticket System

> **Complexity**: Intermediate | **Entities**: 3 | **DSL Lines**: ~190

A multi-entity support ticket application demonstrating entity relationships and foreign key references. This example builds on `contact_manager` by introducing multiple related entities.

## Quick Start

```bash
cd examples/support_tickets
dazzle serve
```

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

## What This Example Demonstrates

### DSL Features

| Feature | Usage |
|---------|-------|
| **Foreign Key References** | `created_by: ref User required` |
| **Optional References** | `assigned_to: ref User` (nullable) |
| **Multi-Column Indexes** | `index status, priority` |
| **Multiple Entities** | User, Ticket, Comment |
| **Full CRUD for All Entities** | 12 surfaces total (4 per entity) |

### Building on contact_manager

This example adds:

1. **Entity relationships** - Tickets reference Users, Comments reference Tickets
2. **Required vs optional refs** - `created_by` is required, `assigned_to` is optional
3. **Complex domain** - 3 entities with interconnected relationships
4. **Database indexes** - Composite indexes for query optimization

## Entity Relationship Diagram

```
User (1)
  │
  ├──< created_by ──< Ticket (many)
  │                      │
  ├──< assigned_to ──────┤
  │                      │
  └──< author ────< Comment (many) ───< ticket ──┘
```

**Relationships**:

- User → Ticket: One user can create many tickets
- User → Ticket: One user can be assigned many tickets
- Ticket → Comment: One ticket can have many comments
- User → Comment: One user can author many comments

## Key DSL Patterns

### Required Reference (Foreign Key)

```dsl
entity Ticket "Support Ticket":
  created_by: ref User required
  # Every ticket must have a creator
  # Cannot be null
```

### Optional Reference

```dsl
entity Ticket "Support Ticket":
  assigned_to: ref User
  # Ticket can be unassigned
  # Can be null
```

### Composite Index

```dsl
entity Ticket "Support Ticket":
  ...
  index status, priority
  # Optimizes queries filtering by both fields
```

### One-to-Many via Back Reference

```dsl
entity Comment "Comment":
  ticket: ref Ticket required
  author: ref User required
  # Comment belongs to one ticket
  # Comment authored by one user
```

## User Stories

| ID | Story | Entities Involved |
|----|-------|-------------------|
| US-1 | Submit support request | User, Ticket |
| US-2 | View ticket queue | Ticket |
| US-3 | Assign ticket to staff | Ticket, User |
| US-4 | Add comment to ticket | Ticket, Comment, User |
| US-5 | Resolve and close ticket | Ticket |

## Learning Path

**Previous**: [Contact Manager](contact-manager.md) (Beginner+) - Single entity, indexes, workspaces

**Next**: [Ops Dashboard](ops-dashboard.md) (Intermediate+) - Personas, COMMAND_CENTER archetype

## Key Learnings

1. **`ref` creates foreign keys**
   - `ref Entity` creates a nullable foreign key
   - `ref Entity required` creates a non-null foreign key

2. **Entities can reference the same entity multiple times**
   - Ticket has both `created_by` and `assigned_to` referencing User
   - Each creates a separate relationship

3. **Comments show nested relationships**
   - Comment → Ticket → User (creator)
   - Comment → User (author)
   - Multi-level entity graph

4. **Indexes optimize common queries**
   - `index status, priority` for ticket queue views
   - `index created_by` for "my tickets" queries

## API Endpoints

With 3 entities, DNR generates 12 CRUD endpoints:

| Entity | Endpoints |
|--------|-----------|
| User | `GET/POST /api/users`, `GET/PUT/DELETE /api/users/{id}` |
| Ticket | `GET/POST /api/tickets`, `GET/PUT/DELETE /api/tickets/{id}` |
| Comment | `GET/POST /api/comments`, `GET/PUT/DELETE /api/comments/{id}` |

## Customization Ideas

Try modifying this example:

1. Add an `Attachment` entity with `ref Ticket`
2. Add ticket categories as a separate entity
3. Add an attention signal for unassigned critical tickets
4. Create a workspace for "My Assigned Tickets"
