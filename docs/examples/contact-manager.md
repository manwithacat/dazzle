# Contact Manager

> Multi-entity CRUD with the DUAL_PANE_FLOW archetype - list + detail pattern.

## Quick Start

```bash
cd examples/contact_manager
dazzle serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Overview

| Attribute | Value |
|-----------|-------|
| **Complexity** | Beginner |
| **CI Priority** | P0 (blocks PRs) |
| **Archetype** | DUAL_PANE_FLOW |
| **Entities** | Contact |
| **Workspaces** | contacts |

## DSL Specification

**Source**: [examples/contact_manager/dsl/app.dsl](https://github.com/manwithacat/dazzle/blob/main/examples/contact_manager/dsl/app.dsl)

### Entity: Contact

```dsl
entity Contact "Contact":
  id: uuid pk
  first_name: str(100) required
  last_name: str(100) required
  email: email unique required
  phone: str(20)
  company: str(200)
  job_title: str(150)
  notes: text
  is_favorite: bool=false
  created_at: datetime auto_add
  updated_at: datetime auto_update

  index email
  index last_name,first_name
```

### Workspace: Contacts

```dsl
workspace contacts "Contacts":
  purpose: "Browse contacts and view details"

  # List signal - browsable contact list
  contact_list:
    source: Contact
    limit: 20

  # Detail signal - selected contact details
  contact_detail:
    source: Contact
    display: detail
```

## Archetype Analysis

This example demonstrates the **DUAL_PANE_FLOW** archetype:

- **List Signal Weight**: 0.6 (base 0.5 + limit 0.1)
- **Detail Signal Weight**: 0.7 (base 0.5 + detail display 0.2)

**Layout Behavior**:
- Desktop: Side-by-side list and detail panes
- Mobile: Stacked view, detail slides over list on selection

## E2E Test Coverage

| Metric | Coverage |
|--------|----------|
| Routes | 6 |
| CRUD Operations | Full |
| Components | 6 |

### Test Commands

```bash
dazzle test generate -o testspec.json
dazzle test run --verbose
dazzle test list
```

## Screenshots

### Dashboard
![Dashboard](https://raw.githubusercontent.com/manwithacat/dazzle/main/examples/contact_manager/screenshots/dashboard.png)

### List View
![List View](https://raw.githubusercontent.com/manwithacat/dazzle/main/examples/contact_manager/screenshots/list_view.png)

### Create Form
![Create Form](https://raw.githubusercontent.com/manwithacat/dazzle/main/examples/contact_manager/screenshots/create_form.png)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/contacts` | List all contacts |
| POST | `/api/contacts` | Create a contact |
| GET | `/api/contacts/{id}` | Get contact by ID |
| PUT | `/api/contacts/{id}` | Update contact |
| DELETE | `/api/contacts/{id}` | Delete contact |

## Related Examples

- [Simple Task](simple-task.md) - Basic CRUD app
- [Support Tickets](support-tickets.md) - Foreign key relationships
