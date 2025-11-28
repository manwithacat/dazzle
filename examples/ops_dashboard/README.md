# Operations Dashboard Example

This example demonstrates the **COMMAND_CENTER** archetype - a dense, expert-focused dashboard designed for operations monitoring and incident response.

## Archetype: COMMAND_CENTER

The Command Center archetype is optimized for:
- **Expert users** who need comprehensive system visibility
- **Real-time monitoring** with critical alert handling
- **High information density** without overwhelming the user
- **Quick actions** for immediate response

### Layout Structure

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

### Surfaces

| Surface | Capacity | Priority | Purpose |
|---------|----------|----------|---------|
| `header` | 0.4 | 3 | Critical alerts and status indicators |
| `main_grid` | 1.5 | 1 | Dense grid of metrics and charts |
| `left_rail` | 0.6 | 2 | Quick actions and navigation |
| `right_rail` | 0.6 | 2 | Contextual information and tools |

## Features Demonstrated

### Real-Time Alerts
- Critical alert banner with acknowledgment
- Severity-based styling (low, medium, high, critical)
- Alert filtering by acknowledged status

### System Monitoring
- Health status indicators (healthy, degraded, critical, offline)
- Response time tracking
- Error rate monitoring
- CPU/memory usage

### Expert UX
- Dense information layout
- Keyboard shortcuts hint
- Quick action sidebar
- Contextual details panel

## Running the Example

```bash
# Navigate to example
cd examples/ops_dashboard

# Validate the DSL
dazzle validate

# View layout plan
dazzle layout-plan -w command_center

# Generate Next.js app
dazzle build --stack nextjs_semantic

# Run the generated app
cd build/nextjs_semantic/ops-dashboard
npm install
npm run dev
```

## DSL Highlights

### Engine Hint

The `engine_hint` forces selection of COMMAND_CENTER archetype:

```dsl
workspace command_center "Command Center":
  purpose: "Real-time operations monitoring"
  engine_hint: "command_center"
```

### Expert Persona

```dsl
persona ops_engineer "Operations Engineer":
  proficiency_level: expert
  session_style: deep_work
```

### Multiple Data Regions

```dsl
workspace command_center "Command Center":
  # Alert feed
  active_alerts:
    source: Alert
    filter: acknowledged = false
    sort: severity desc, triggered_at desc
    limit: 20
  
  # System status grid
  system_status:
    source: System
    sort: status asc, name asc
  
  # Aggregate health metrics
  health_summary:
    source: System
    aggregate:
      total_systems: count(System)
      healthy_count: count(System WHERE status = 'healthy')
      critical_count: count(System WHERE status = 'critical')
```

## When to Use COMMAND_CENTER

**Use when**:
- Users are experts who need dense information
- Real-time monitoring is critical
- Multiple alert streams need attention
- Quick response actions are required
- Users have large screens (desktop-focused)

**Avoid when**:
- Users are novice or casual
- Information needs are simple
- Mobile is primary platform
- Glance-based usage (use FOCUS_METRIC instead)

## Layout Plan Output

```
Workspace: command_center
============================================================
Label: Command Center
Archetype: command_center
Attention Budget: 1.0

Attention Signals:
  - active_alerts (item_list) Weight: 0.80
  - system_status (table) Weight: 0.50
  - health_summary (kpi) Weight: 0.70

Surface Allocation:
  - main_grid: active_alerts, health_summary
  - left_rail: system_status
  - right_rail: (none)
  - header: (none)
```

## Files

- `dazzle.toml` - Project configuration
- `dsl/app.dsl` - DSL specification with entities, workspace, and surfaces
- `README.md` - This file
