# Uptime Monitor

> FOCUS_METRIC workspace archetype - single dominant KPI with minimal supporting context.

## Quick Start

```bash
cd examples/uptime_monitor
dazzle dnr serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Overview

| Attribute | Value |
|-----------|-------|
| **Complexity** | Intermediate |
| **CI Priority** | P1 |
| **Archetype** | FOCUS_METRIC |
| **Entities** | Service |
| **Workspaces** | uptime |

## DSL Specification

**Source**: [`examples/uptime_monitor/dsl/app.dsl`](../../../examples/uptime_monitor/dsl/app.dsl)

### Entity: Service

```dsl
entity Service "Service":
  id: uuid pk
  name: str(200) required
  endpoint: str(500) required
  status: enum[up,down,degraded]=up
  uptime_percentage: decimal(5,2)
  last_check: datetime auto_update
  created_at: datetime auto_add
```

### Workspace: System Uptime

```dsl
workspace uptime "System Uptime":
  purpose: "Monitor overall system availability"

  # Single critical metric - triggers FOCUS_METRIC
  system_uptime:
    source: Service
    aggregate:
      average_uptime: avg(uptime_percentage)
      total_services: count(Service)
      services_down: count(Service WHERE status = 'down')
```

## Archetype Analysis

This example demonstrates the **FOCUS_METRIC** archetype:

- Single aggregate signal with multiple KPIs
- Hero metric layout with primary focus on `average_uptime`
- Supporting metrics shown as secondary context

**Use Cases**:
- Executive dashboards
- SLA monitoring
- Critical system health displays

## E2E Test Coverage

| Metric | Coverage |
|--------|----------|
| Routes | 4 |
| CRUD Operations | Full |
| Components | 4 |

## Screenshots

*Screenshots are generated automatically during CI.*

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/services` | List all services |
| POST | `/api/services` | Create a service |
| GET | `/api/services/{id}` | Get service by ID |
| PUT | `/api/services/{id}` | Update service |
| DELETE | `/api/services/{id}` | Delete service |

## Related Examples

- [Ops Dashboard](../ops_dashboard/) - COMMAND_CENTER archetype (8+ signals)
- [Inventory Scanner](../inventory_scanner/) - SCANNER_TABLE archetype
