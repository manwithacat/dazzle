# Email Client

> MONITOR_WALL workspace archetype - multiple moderate signals in a dashboard layout.

## Quick Start

```bash
cd examples/email_client
dazzle dnr serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Overview

| Attribute | Value |
|-----------|-------|
| **Complexity** | Intermediate |
| **CI Priority** | P2 |
| **Archetype** | MONITOR_WALL |
| **Entities** | Message |
| **Workspaces** | inbox |

## DSL Specification

**Source**: [`examples/email_client/dsl/app.dsl`](../../../examples/email_client/dsl/app.dsl)

### Entity: Message

```dsl
entity Message "Message":
  id: uuid pk
  subject: str(200) required
  sender: str(200) required
  recipient: str(200) required
  body: text required
  status: enum[unread,read,archived]=unread
  priority: enum[low,normal,high]=normal
  received_at: datetime auto_add
  read_at: datetime optional
```

### Workspace: Email Inbox

```dsl
workspace inbox "Email Inbox":
  purpose: "Monitor emails across multiple views"

  # Unread count KPI
  unread_stats:
    source: Message
    aggregate:
      total_unread: count(Message WHERE status = 'unread')
      high_priority: count(Message WHERE priority = 'high')

  # Recent unread messages
  recent_unread:
    source: Message
    limit: 10

  # High priority messages
  priority_messages:
    source: Message
    limit: 5

  # All messages table
  all_messages:
    source: Message
```

## Archetype Analysis

This example demonstrates the **MONITOR_WALL** archetype:

- 3-5 moderate-weight signals
- Balanced dashboard layout
- Multiple views of the same data with different filters

**Use Cases**:
- Operations dashboards
- Notification centers
- Multi-panel monitoring
- Email/messaging interfaces

## E2E Test Coverage

| Metric | Coverage |
|--------|----------|
| Routes | 5 |
| CRUD Operations | Partial |
| Components | 5 |

## Screenshots

### Dashboard
![Dashboard](../../../examples/email_client/screenshots/dashboard.png)

### List View
![List View](../../../examples/email_client/screenshots/list_view.png)

### Create Form
![Create Form](../../../examples/email_client/screenshots/create_form.png)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/messages` | List all messages |
| POST | `/api/messages` | Create a message |
| GET | `/api/messages/{id}` | Get message by ID |
| PUT | `/api/messages/{id}` | Update message |
| DELETE | `/api/messages/{id}` | Delete message |

## Related Examples

- [Ops Dashboard](../ops_dashboard/) - COMMAND_CENTER archetype (8+ signals)
- [Uptime Monitor](../uptime_monitor/) - FOCUS_METRIC archetype
