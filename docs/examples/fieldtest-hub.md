# FieldTest Hub

> **Complexity**: Advanced | **Entities**: 6 | **DSL Lines**: ~680

A distributed beta testing platform for hardware field testing. This is the most comprehensive example, demonstrating a complex multi-entity domain with persona-aware surface scoping, access rules, and multiple workspaces.

## Quick Start

```bash
cd examples/fieldtest_hub
dazzle serve
```

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

## What This Example Demonstrates

### DSL Features

| Feature | Usage |
|---------|-------|
| **6-Entity Domain** | Device, Tester, IssueReport, TestSession, FirmwareRelease, Task |
| **Persona Scoping** | `for engineer: scope: all` vs `for tester: scope: assigned_tester_id = current_user` |
| **Conditional Attention** | `when: severity = critical and status = open` |
| **Multiple Workspaces** | Engineering Dashboard vs Tester Dashboard |
| **Persona Defaults** | `defaults: reported_by_id: current_user` |
| **Complex Filters** | `filter: severity = critical and status != closed` |

### Building on ops_dashboard

This example adds:

1. **Complex domain** - 6 interconnected entities
2. **Persona scoping** - Different data visibility per user type
3. **Access patterns** - Engineers see all, testers see assigned
4. **Multiple workspaces** - Role-specific dashboards
5. **Form defaults** - Persona-aware field pre-population

## Domain Model

```
Device ─────< IssueReport >───── Tester
   │                │
   │                └─────────── FirmwareRelease
   │
   └────< TestSession >────────── Tester

Task ─────── (created_by, assigned_to)
```

### Entities

| Entity | Purpose | Fields |
|--------|---------|--------|
| **Device** | Hardware being tested | name, model, batch, serial, firmware, status |
| **Tester** | Field testers | name, location, skill_level, active |
| **IssueReport** | Bug/problem reports | device, reporter, severity, category, status |
| **TestSession** | Usage logs | device, tester, duration, environment |
| **FirmwareRelease** | Firmware versions | version, status, release_notes |
| **Task** | Engineering tasks | type, assignee, status |

## Personas

### Engineer

- **Scope**: All data - complete visibility
- **Actions**: Full CRUD on all entities
- **Dashboard**: Engineering Dashboard with metrics and critical issues

### Tester

- **Scope**: Assigned devices and own reports only
- **Actions**: Log issues, record sessions
- **Dashboard**: Tester Dashboard with personal activity

## Persona Scoping Examples

### Surface with Persona Scoping

```dsl
surface device_list "Device Dashboard":
  uses entity Device
  mode: list

  ux:
    for engineer:
      scope: all
      purpose: "Manage all devices across batches"
      action_primary: device_create

    for tester:
      scope: assigned_tester_id = current_user
      purpose: "Your assigned devices"
      show: name, model, firmware_version, status
```

### Form with Persona Defaults

```dsl
surface issue_report_create "Report Issue":
  uses entity IssueReport
  mode: create

  ux:
    for tester:
      defaults:
        reported_by_id: current_user
        severity: medium
```

## Workspaces

### Engineering Dashboard

```dsl
workspace engineering_dashboard "Engineering Dashboard":
  purpose: "Comprehensive field testing oversight"

  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    limit: 10

  metrics:
    source: IssueReport
    aggregate:
      total_issues: count(IssueReport)
      critical: count(IssueReport where severity = critical)
```

### Tester Dashboard

```dsl
workspace tester_dashboard "Tester Dashboard":
  purpose: "Personal field testing hub"

  my_devices:
    source: Device
    filter: assigned_tester_id = current_user
```

## Attention Signals

The example uses multiple attention signal types:

```dsl
# Critical attention - red highlight
attention critical:
  when: severity = critical and status = open
  message: "Critical issue - requires immediate attention"

# Warning attention - orange highlight
attention warning:
  when: severity = high and status = open
  message: "High severity issue"

# Notice attention - blue highlight
attention notice:
  when: status = in_progress and days_since(updated_at) > 3
  message: "Stalled for 3+ days"
```

## Learning Path

**Previous**: [Ops Dashboard](ops-dashboard.md) (Intermediate+) - Personas, engine hints

**This Example**: `fieldtest_hub` (Advanced) - Culmination of all DSL features

## Key Learnings

1. **Persona scoping controls data visibility**
   - `scope: all` for admin access
   - `scope: field = current_user` for personal data

2. **Defaults simplify forms per persona**
   - Pre-populate user-specific fields
   - Set sensible status defaults

3. **Multiple workspaces serve different user needs**
   - Engineering: metrics and critical issues
   - Tester: personal activity and assigned work

4. **Complex domains are declarative**
   - 6 entities, 24 surfaces, 2 workspaces
   - All defined in ~680 lines of DSL

5. **Attention signals guide user focus**
   - Multiple severity levels (critical, warning, notice)
   - Conditional logic with time functions

## API Endpoints

With 6 entities, DNR generates 24 CRUD endpoints:

| Entity | Count |
|--------|-------|
| Device | 4 endpoints |
| Tester | 4 endpoints |
| IssueReport | 4 endpoints |
| TestSession | 4 endpoints |
| FirmwareRelease | 4 endpoints |
| Task | 4 endpoints |
