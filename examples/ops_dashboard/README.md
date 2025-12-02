# Operations Dashboard

> **Complexity**: Intermediate+ | **Entities**: 2 | **DSL Lines**: ~125

A real-time operations monitoring dashboard demonstrating the **COMMAND_CENTER** archetype with personas and engine hints. This example builds on `support_tickets` by introducing expert user personas and dense information layouts.

## Quick Start

```bash
cd examples/ops_dashboard
dazzle dnr serve
```

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

## What This Example Demonstrates

### DSL Features

| Feature | Usage |
|---------|-------|
| **Personas** | `persona ops_engineer` with proficiency and session style |
| **Engine Hints** | `engine_hint: "command_center"` forces archetype |
| **Aggregations** | `count(System)`, `avg(response_time_ms)` |
| **Persona-Scoped UX** | `for ops_engineer: scope: all` |
| **Filtered Signals** | `filter: acknowledged = false` |

### Building on support_tickets

This example adds:
1. **Personas** - User proficiency levels and session styles
2. **Engine hints** - Override automatic archetype selection
3. **Aggregate metrics** - KPI signals from entity data
4. **Expert UX patterns** - Dense interfaces for power users

## The COMMAND_CENTER Archetype

This archetype is optimized for expert users who need:
- High information density
- Real-time monitoring
- Quick alert response
- Multi-system visibility

```
+------------------------------------------------------------------+
|  HEADER: Critical alerts banner + status indicators               |
+------------------------------------------------------------------+
|         |                                    |                    |
| LEFT    |         MAIN GRID                  |      RIGHT         |
| RAIL    |     (2-4 column metrics)           |      RAIL          |
| Quick   |                                    |    Context &       |
| Actions |     System status cards            |    Details         |
|         |     Alert feed                     |                    |
|         |     Key metrics                    |                    |
+------------------------------------------------------------------+
|  FOOTER: System status summary + keyboard shortcuts               |
+------------------------------------------------------------------+
```

## Project Structure

```
ops_dashboard/
├── SPEC.md              # Product specification
├── README.md            # This file
├── dazzle.toml          # Project configuration
└── dsl/
    └── app.dsl          # DAZZLE DSL definition
```

## Key DSL Patterns

### Persona Definition
```dsl
persona ops_engineer "Operations Engineer":
  goals:
    - "Monitor system health in real-time"
    - "Respond quickly to alerts"
  proficiency_level: expert
  session_style: deep_work
```

### Engine Hint for Archetype
```dsl
workspace command_center "Command Center":
  purpose: "Real-time operations monitoring"
  engine_hint: "command_center"
  # Forces COMMAND_CENTER archetype regardless of signal weights
```

### Aggregate Metrics
```dsl
health_summary:
  source: System
  aggregate:
    total_systems: count(System)
    healthy_count: count(System WHERE status = 'healthy')
    critical_count: count(System WHERE status = 'critical')
    avg_response_time: avg(response_time_ms)
```

### Persona-Scoped UX
```dsl
ux:
  for ops_engineer:
    scope: all
    purpose: "Full visibility into all systems and alerts"
```

## User Stories

| ID | Story | Key Feature |
|----|-------|-------------|
| US-1 | Monitor system health | Status grid, color coding |
| US-2 | Respond to alerts | Alert feed, acknowledgment |
| US-3 | View system details | Drill-down to metrics |
| US-4 | View health summary | KPI aggregations |

## Running Tests

```bash
# Validate DSL
dazzle validate

# Run API tests
dazzle dnr test
```

## Learning Path

**Previous**: `support_tickets` (Intermediate) - Entity relationships, refs

**Next**: `fieldtest_hub` (Advanced) - Complex domain, access rules, persona scoping

## Key Learnings

1. **Personas define user context**
   - `proficiency_level` affects UI complexity
   - `session_style` affects information density
   - Used in persona-scoped UX blocks

2. **Engine hints override auto-selection**
   - Normally archetype is selected from signal weights
   - `engine_hint` forces specific archetype

3. **Aggregations create KPI signals**
   - `aggregate:` block with count/avg/sum functions
   - Creates health_summary signal type

4. **Expert UX is dense but organized**
   - Multiple signals visible simultaneously
   - Quick actions without confirmation dialogs
   - Keyboard shortcuts expected

## Workspace Signals

| Signal | Type | Weight | Purpose |
|--------|------|--------|---------|
| `active_alerts` | Item List | 0.80 | Unacknowledged alerts |
| `system_status` | Table | 0.50 | All systems with status |
| `health_summary` | KPI | 0.70 | Aggregate health metrics |

## When to Use COMMAND_CENTER

**Use when**:
- Users are experts needing dense information
- Real-time monitoring is critical
- Multiple alert streams need attention
- Desktop is primary platform

**Avoid when**:
- Users are novice or casual
- Mobile is primary platform
- Glance-based usage (use FOCUS_METRIC instead)

## Screenshots

### Command Center
![Command Center](screenshots/dashboard.png)

### Alert List
![Alert List](screenshots/alert_list.png)

---

*Part of the DAZZLE Examples collection. See `/examples/README.md` for the full learning path.*
