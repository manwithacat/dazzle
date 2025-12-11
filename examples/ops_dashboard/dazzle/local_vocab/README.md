# Ops Dashboard - Vocabulary Reference

Domain-specific patterns for operations monitoring, alerting, and incident response.

## Available Entries

### Common Data Patterns

#### `audit_fields` (macro)
Standard audit timestamp fields.
```dsl
@use audit_fields()
# Expands to:
# created_at: datetime auto_add
# updated_at: datetime auto_update
```

### Monitoring-Specific Patterns

#### `system_status_enum` (macro)
System health status enum.
```dsl
@use system_status_enum()
# Expands to: status: enum[healthy,degraded,critical,offline]=healthy

@use system_status_enum(default_value=degraded)
# Different default
```

#### `service_type_enum` (macro)
Service type classification.
```dsl
@use service_type_enum()
# Expands to: service_type: enum[web,api,database,cache,queue]=web
```

#### `severity_enum` (macro)
Alert severity levels.
```dsl
@use severity_enum()
# Expands to: severity: enum[low,medium,high,critical]=low
```

#### `metric_fields` (macro)
Common performance metric fields.
```dsl
@use metric_fields()
# Expands to:
# response_time_ms: int
# error_rate: decimal(5,2)
# cpu_usage: decimal(5,2)
# memory_usage: decimal(5,2)
```

#### `acknowledgment_fields` (macro)
Alert acknowledgment tracking.
```dsl
@use acknowledgment_fields()
# Expands to:
# acknowledged: bool = false
# acknowledged_by: str(200)
```

### Entity Templates

#### `system_entity` (pattern)
Monitored system entity with status and metrics.
```dsl
@use system_entity()
# Generates complete System entity with:
# - id, name, service_type, status
# - response_time_ms, error_rate, cpu_usage, memory_usage
# - last_check, created_at

@use system_entity(entity_name=Service)
# Creates Service entity instead
```

#### `alert_entity` (pattern)
Alert entity for system monitoring.
```dsl
@use alert_entity()
# Generates complete Alert entity with:
# - id, system ref, severity, message
# - triggered_at, acknowledged, acknowledged_by

@use alert_entity(entity_name=Incident, system_entity=Service)
# Custom entity names
```

### UI Patterns

#### `crud_surface_set` (pattern)
Complete CRUD surface set.
```dsl
@use crud_surface_set(entity_name=System, title_field=name)
```

#### `command_center_workspace` (pattern)
Command center workspace with monitoring panels.
```dsl
@use command_center_workspace()
# Generates workspace with:
# - active_alerts (unacknowledged alerts)
# - system_status (all systems)
# - health_summary (aggregated metrics)
```

## Usage Example

```dsl
module ops.core
app ops_dashboard "Operations Dashboard"

# Generate monitoring entities
@use system_entity()
@use alert_entity()

# Generate command center
@use command_center_workspace()

# Generate CRUD surfaces
@use crud_surface_set(entity_name=System, title_field=name)
@use crud_surface_set(entity_name=Alert, title_field=message)
```

## Commands

```bash
dazzle vocab list              # List all entries
dazzle vocab show system_entity   # Show entry details
dazzle vocab list --tag ops    # Filter by tag
```

## Tags

- `ops`, `monitoring` - Operations-specific patterns
- `alerting`, `severity` - Alert management
- `metrics`, `performance` - Performance tracking
- `command_center` - Dashboard patterns
