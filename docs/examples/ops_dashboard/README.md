# Operations Dashboard

> COMMAND_CENTER workspace archetype - dense expert interface for operations monitoring.

## Quick Start

```bash
cd examples/ops_dashboard
dazzle dnr serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Overview

| Attribute | Value |
|-----------|-------|
| **Complexity** | Advanced |
| **CI Priority** | P2 |
| **Archetype** | COMMAND_CENTER |
| **Entities** | System, Alert |
| **Workspaces** | command_center |
| **Personas** | ops_engineer |

## DSL Specification

**Source**: [`examples/ops_dashboard/dsl/app.dsl`](../../../examples/ops_dashboard/dsl/app.dsl)

### Entity: System

```dsl
entity System "System":
  id: uuid pk
  name: str(200) required
  service_type: enum[web,api,database,cache,queue]=web
  status: enum[healthy,degraded,critical,offline]=healthy
  response_time_ms: int
  error_rate: decimal(5,2)
  cpu_usage: decimal(5,2)
  memory_usage: decimal(5,2)
  last_check: datetime auto_update
  created_at: datetime auto_add
```

### Entity: Alert

```dsl
entity Alert "Alert":
  id: uuid pk
  system: ref System required
  severity: enum[low,medium,high,critical]=low
  message: str(500) required
  triggered_at: datetime auto_add
  acknowledged: bool = false
  acknowledged_by: str(200)
```

### Persona: Operations Engineer

```dsl
persona ops_engineer "Operations Engineer":
  goals:
    - "Monitor system health in real-time"
    - "Respond quickly to alerts"
  proficiency_level: expert
  session_style: deep_work
```

### Workspace: Command Center

```dsl
workspace command_center "Command Center":
  purpose: "Real-time operations monitoring and incident response"
  engine_hint: "command_center"

  active_alerts:
    source: Alert
    filter: acknowledged = false
    sort: severity desc, triggered_at desc
    limit: 20

  system_status:
    source: System
    sort: status asc, name asc

  health_summary:
    source: System
    aggregate:
      total_systems: count(System)
      healthy_count: count(System WHERE status = 'healthy')
      critical_count: count(System WHERE status = 'critical')
      avg_response_time: avg(response_time_ms)

  ux:
    for ops_engineer:
      scope: all
      purpose: "Full visibility into all systems and alerts"
```

## Archetype Analysis

This example demonstrates the **COMMAND_CENTER** archetype:

- 8+ signals with high information density
- Expert-oriented interface
- Real-time monitoring focus
- Persona-driven UX customization

**Use Cases**:
- DevOps monitoring
- Network operations centers
- System health dashboards
- Incident response interfaces

## Advanced Features

### Persona Integration

The `ops_engineer` persona influences:
- Information density (expert level)
- Session style (deep work - extended monitoring)
- UX scope (full visibility)

### Engine Hints

The `engine_hint: "command_center"` explicitly requests the COMMAND_CENTER archetype for maximum information density.

## E2E Test Coverage

| Metric | Coverage |
|--------|----------|
| Routes | 8 |
| CRUD Operations | Partial |
| Components | 8 |

## Screenshots

### Dashboard
![Dashboard](../../../examples/ops_dashboard/screenshots/dashboard.png)

### List View
![List View](../../../examples/ops_dashboard/screenshots/list_view.png)

### Create Form
![Create Form](../../../examples/ops_dashboard/screenshots/create_form.png)

## API Endpoints

### Systems
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/systems` | List all systems |
| POST | `/api/systems` | Create a system |
| GET | `/api/systems/{id}` | Get system by ID |
| PUT | `/api/systems/{id}` | Update system |
| DELETE | `/api/systems/{id}` | Delete system |

### Alerts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/alerts` | List all alerts |
| POST | `/api/alerts` | Create an alert |
| GET | `/api/alerts/{id}` | Get alert by ID |
| PUT | `/api/alerts/{id}` | Update/acknowledge alert |
| DELETE | `/api/alerts/{id}` | Delete alert |

## Related Examples

- [Email Client](../email_client/) - MONITOR_WALL archetype (3-5 signals)
- [Uptime Monitor](../uptime_monitor/) - FOCUS_METRIC archetype (single KPI)
