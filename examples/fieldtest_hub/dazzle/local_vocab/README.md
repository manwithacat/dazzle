# FieldTest Hub - Vocabulary Reference

Domain-specific patterns for hardware field testing, beta programs, and device management.

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

### Field Testing Patterns

#### `device_status_enum` (macro)
Device lifecycle status.
```dsl
@use device_status_enum()
# Expands to: status: enum[prototype,active,recalled,retired]=prototype
```

#### `issue_status_enum` (macro)
Issue report lifecycle status.
```dsl
@use issue_status_enum()
# Expands to: status: enum[open,triaged,in_progress,fixed,verified,closed]=open
```

#### `severity_enum` (macro)
Issue severity levels.
```dsl
@use severity_enum()
# Expands to: severity: enum[low,medium,high,critical]=medium
```

#### `issue_category_enum` (macro)
Hardware issue category classification.
```dsl
@use issue_category_enum()
# Expands to: category: enum[battery,connectivity,mechanical,overheating,crash,other]=other
```

#### `skill_level_enum` (macro)
Tester skill level.
```dsl
@use skill_level_enum()
# Expands to: skill_level: enum[casual,enthusiast,engineer]=casual
```

#### `environment_enum` (macro)
Testing environment classification.
```dsl
@use environment_enum()
# Expands to: environment: enum[indoor,outdoor,vehicle,industrial,other]=indoor
```

#### `firmware_fields` (macro)
Firmware and batch tracking.
```dsl
@use firmware_fields()
# Expands to:
# firmware_version: str(50)
# batch_number: str(100) required
```

#### `photo_url_field` (alias)
URL field for evidence photos.
```dsl
@use photo_url_field()
# Expands to: photo_url: str(500)

@use photo_url_field(field_name=evidence_url)
# Custom field name
```

#### `active_status_field` (alias)
Active/inactive boolean flag.
```dsl
@use active_status_field()
# Expands to: active: bool=true
```

### Entity Templates

#### `device_entity` (pattern)
Field test device with tracking.
```dsl
@use device_entity()
# Generates complete Device entity with:
# - id, name, model, batch_number, serial_number
# - firmware_version, status, assigned_tester_id
# - deployed_at, timestamps
```

#### `tester_entity` (pattern)
Field tester with skill and location.
```dsl
@use tester_entity()
# Generates complete Tester entity with:
# - id, name, email, location
# - skill_level, joined_at, active
# - timestamps
```

#### `issue_report_entity` (pattern)
Issue report for field testing feedback.
```dsl
@use issue_report_entity()
# Generates complete IssueReport entity with:
# - id, device_id, reported_by_id
# - category, severity, description
# - steps_to_reproduce, photo_url
# - status, resolution, firmware_version
# - timestamps
```

#### `test_session_entity` (pattern)
Test session log for device usage.
```dsl
@use test_session_entity()
# Generates complete TestSession entity with:
# - id, device_id, tester_id
# - duration_minutes, environment, temperature
# - notes, logged_at, timestamps
```

### UI Patterns

#### `crud_surface_set` (pattern)
Complete CRUD surface set.
```dsl
@use crud_surface_set(entity_name=Device, title_field=name)
```

## Usage Example

```dsl
module fieldtest.core
app fieldtest_hub "FieldTest Hub"

# Generate all core entities
@use device_entity()
@use tester_entity()
@use issue_report_entity()
@use test_session_entity()

# Generate CRUD surfaces
@use crud_surface_set(entity_name=Device, title_field=name)
@use crud_surface_set(entity_name=Tester, title_field=name)
@use crud_surface_set(entity_name=IssueReport, title_field=description)
@use crud_surface_set(entity_name=TestSession, title_field=notes)
```

## Commands

```bash
dazzle vocab list                # List all entries
dazzle vocab show device_entity  # Show entry details
dazzle vocab list --tag fieldtest   # Filter by tag
```

## Tags

- `fieldtest`, `hardware` - Field testing patterns
- `device`, `tester`, `issue` - Entity-specific
- `lifecycle`, `status` - Status tracking
- `testing`, `session` - Session management
