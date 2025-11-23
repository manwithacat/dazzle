# Urban Canopy - Vocabulary Reference

**Focus**: Location-based asset tracking and field service patterns
**Reusability**: High - applicable to many domains beyond urban planning

This vocabulary contains **generic patterns** useful for:
- 🌳 Urban planning & environmental management
- 🏢 Facilities & equipment management
- 🚗 Fleet & vehicle tracking
- 🏪 Store & venue location management
- 🔧 Field service & inspections
- 👥 Volunteer & member coordination
- 📦 Asset & inventory tracking

## Available Entries (15)

### Location Patterns (3 entries)

#### `geo_location_fields` (macro)
Geographic coordinates for any location-based entity.
```dsl
entity Store:
  @use geo_location_fields()
  # Expands to:
  # location_lat: decimal(9,6) required
  # location_lng: decimal(9,6) required

# Custom field names
@use geo_location_fields(lat_field=lat, lng_field=lng, required=false)
```

**Use cases**: Stores, venues, equipment, trees, poles, facilities, vehicles

#### `address_field` (alias)
Physical street address.
```dsl
@use address_field()
# Expands to: street_address: str(300)

@use address_field(field_name=mailing_address, max_length=500, required=true)
```

**Use cases**: Any entity with a physical location

#### `full_location_fields` (pattern)
Complete location (coordinates + address).
```dsl
entity Location:
  @use full_location_fields()
  # Expands to:
  # location_lat: decimal(9,6) required
  # location_lng: decimal(9,6) required
  # street_address: str(300)

@use full_location_fields(coordinates_required=true, address_required=true)
```

**Use cases**: Primary location entities in any location-centric app

### Asset Tracking Patterns (3 entries)

#### `audit_fields` (macro)
Standard timestamps for any entity.
```dsl
@use audit_fields()
# Expands to:
# created_at: datetime auto_add
# updated_at: datetime auto_update
```

**Use cases**: Every entity that needs change tracking

#### `condition_status_enum` (macro)
Physical condition for assets.
```dsl
@use condition_status_enum()
# Expands to: condition_status: enum[Excellent,Good,Fair,Poor,Critical]=Good

@use condition_status_enum(field_name=health_status, default_value=Fair)
```

**Use cases**: Trees, equipment, vehicles, buildings, infrastructure, inventory

#### `inspection_tracking` (macro)
Last inspection details.
```dsl
@use inspection_tracking()
# Expands to:
# last_inspection_date: datetime optional
# last_inspector: ref User

@use inspection_tracking(inspector_entity=Volunteer)
```

**Use cases**: Assets requiring periodic inspection/maintenance

### Media & Documentation (3 entries)

#### `photo_url_field` (alias)
Photo attachment field.
```dsl
@use photo_url_field()
# Expands to: photo_url: str(500)

@use photo_url_field(field_name=thumbnail_url, required=true)
```

**Use cases**: Observations, inspections, inventory, real estate, products

#### `document_url_field` (alias)
Document attachment field.
```dsl
@use document_url_field()
# Expands to: document_url: str(500)

@use document_url_field(field_name=manual_url)
```

**Use cases**: Equipment manuals, permits, certificates, reports

#### `media_fields` (macro)
Both photo and document fields.
```dsl
@use media_fields()
# Expands to:
# photo_url: str(500)
# document_url: str(500)
```

**Use cases**: Entities that need multiple attachment types

### Task & Assignment Patterns (2 entries)

#### `task_status_enum` (macro)
Generic task/work order status.
```dsl
@use task_status_enum()
# Expands to: status: enum[Open,InProgress,Completed,Cancelled]=Open

@use task_status_enum(field_name=work_order_status, default_value=InProgress)
```

**Use cases**: Maintenance tasks, work orders, service requests, inspections

#### `assignment_fields` (macro)
Track who created and who's assigned.
```dsl
@use assignment_fields()
# Expands to:
# created_by: ref User required
# assigned_to: ref User

@use assignment_fields(user_entity=Volunteer, assignment_required=true)
```

**Use cases**: Tasks, tickets, work orders, assignments, delegations

### Member/Volunteer Patterns (2 entries)

#### `active_status_field` (alias)
Active/inactive flag for people or resources.
```dsl
@use active_status_field()
# Expands to: is_active: bool=true

@use active_status_field(field_name=is_available, default_value=false)
```

**Use cases**: Members, volunteers, employees, equipment, subscriptions

#### `joined_at_field` (alias)
Membership start timestamp.
```dsl
@use joined_at_field()
# Expands to: joined_at: datetime auto_add

@use joined_at_field(field_name=enrolled_at)
```

**Use cases**: Members, volunteers, employees, students, subscribers

### Entity Templates (1 entry)

#### `observation_entity` (pattern)
Generic observation/log entry for inspections.
```dsl
@use observation_entity(subject_entity=Tree)
# Generates complete Observation entity with:
# - id, subject ref, observer, notes, photo_url, submitted_at

@use observation_entity(
  entity_name=Inspection,
  subject_entity=Equipment,
  subject_field=equipment,
  observer_entity=Inspector
)
```

**Use cases**: Field inspections, quality checks, condition reports, audits

### UI Patterns (1 entry)

#### `crud_surface_set` (pattern)
Complete CRUD surfaces (same as other examples).
```dsl
@use crud_surface_set(entity_name=Tree, title_field=species)
```

## Usage Examples

### Example 1: Urban Canopy - Tree Entity (Simplified)
```dsl
entity Tree "Tree":
  id: uuid pk
  species: str(200) required
  @use full_location_fields(coordinates_required=true)
  @use condition_status_enum()
  @use inspection_tracking(inspector_entity=Volunteer)
  @use audit_fields()
  steward: ref Volunteer
```

### Example 2: Facilities Management - Equipment Tracking
```dsl
module facilities.core
app facilities_manager "Facilities Manager"

entity Equipment "Equipment":
  id: uuid pk
  name: str(200) required
  equipment_type: str(100) required
  @use full_location_fields()
  @use condition_status_enum()
  @use inspection_tracking()
  @use audit_fields()

entity MaintenanceTask "Maintenance Task":
  id: uuid pk
  equipment: ref Equipment required
  task_type: str(100) required
  @use task_status_enum()
  @use assignment_fields()
  @use audit_fields()

@use observation_entity(subject_entity=Equipment, observer_entity=Technician)
```

### Example 3: Fleet Management - Vehicle Tracking
```dsl
entity Vehicle "Vehicle":
  id: uuid pk
  make: str(100) required
  model: str(100) required
  vin: str(17) required unique
  @use geo_location_fields()  # Current location
  @use condition_status_enum()
  @use inspection_tracking()
  @use active_status_field(field_name=in_service)
  @use audit_fields()

entity ServiceLog "Service Log":
  id: uuid pk
  vehicle: ref Vehicle required
  @use task_status_enum()
  @use assignment_fields(user_entity=Mechanic)
  @use media_fields()  # Photos and documents
  @use audit_fields()
```

### Example 4: Store Locator - Retail Locations
```dsl
entity Store "Store":
  id: uuid pk
  name: str(200) required
  store_code: str(20) required unique
  @use full_location_fields(coordinates_required=true, address_required=true)
  @use active_status_field(field_name=is_open)
  phone: str(20)
  @use audit_fields()

@use crud_surface_set(entity_name=Store, title_field=name)
```

### Example 5: Volunteer Coordination
```dsl
entity Volunteer "Volunteer":
  id: uuid pk
  name: str(200) required
  email: email unique?
  skill_level: enum[Beginner,Intermediate,Expert]=Beginner
  @use active_status_field()
  @use joined_at_field()
  preferred_area: str(300)

entity Assignment "Assignment":
  id: uuid pk
  volunteer: ref Volunteer required
  task_description: text required
  @use task_status_enum()
  @use geo_location_fields(required=false)
  @use audit_fields()
```

### Example 6: Property Management - Building Inspections
```dsl
entity Building "Building":
  id: uuid pk
  name: str(200) required
  @use full_location_fields(coordinates_required=true)
  @use condition_status_enum()
  building_type: enum[Residential,Commercial,Industrial]
  @use audit_fields()

@use observation_entity(
  entity_name=BuildingInspection,
  subject_entity=Building,
  subject_field=building,
  observer_entity=Inspector
)

entity MaintenanceRequest "Maintenance Request":
  id: uuid pk
  building: ref Building required
  issue_type: str(100) required
  @use task_status_enum()
  @use assignment_fields(user_entity=Technician)
  @use photo_url_field(required=true)
  @use audit_fields()
```

## Cross-Domain Applicability

| Pattern | Urban Planning | Facilities | Fleet | Retail | Field Service |
|---------|----------------|------------|-------|--------|---------------|
| geo_location_fields | ✓ Trees, parks | ✓ Equipment | ✓ Vehicles | ✓ Stores | ✓ Service sites |
| full_location_fields | ✓ Sites | ✓ Buildings | ✓ Depots | ✓ Locations | ✓ Job sites |
| condition_status_enum | ✓ Tree health | ✓ Equipment | ✓ Vehicle | ✓ Inventory | ✓ Assets |
| inspection_tracking | ✓ Tree inspections | ✓ Safety checks | ✓ Inspections | ✓ Audits | ✓ Site visits |
| task_status_enum | ✓ Maintenance | ✓ Work orders | ✓ Service | ✓ Tasks | ✓ Jobs |
| assignment_fields | ✓ Volunteers | ✓ Technicians | ✓ Drivers | ✓ Staff | ✓ Technicians |
| observation_entity | ✓ Tree obs. | ✓ Inspections | ✓ Logs | ✓ Reports | ✓ Notes |

## Commands

```bash
# List all vocabulary
dazzle vocab list

# By category
dazzle vocab list --scope data
dazzle vocab list --tag location
dazzle vocab list --tag asset

# Show specific entries
dazzle vocab show geo_location_fields
dazzle vocab show observation_entity
dazzle vocab show full_location_fields

# Expand to see generated DSL
dazzle vocab expand dsl/app.dsl

# Validate and build
dazzle validate
dazzle build
```

## Tags for Discovery

- **location, geospatial, coordinates, address** - Location-related fields
- **asset, condition, inspection, tracking** - Asset management
- **media, photo, document, attachment** - File attachments
- **task, workflow, assignment, status** - Work/task management
- **member, volunteer** - People management
- **audit, timestamp** - Standard tracking fields
- **common** - Frequently used across domains

```bash
dazzle vocab list --tag location
dazzle vocab list --tag asset
dazzle vocab list --tag common
```

## Why These Patterns?

These vocabulary entries were chosen for their **broad applicability**:

1. **Location patterns** - Core to any location-based app (maps, logistics, field service)
2. **Asset tracking** - Applicable to equipment, vehicles, inventory, infrastructure
3. **Condition monitoring** - Any physical item that degrades over time
4. **Observation/logging** - Field inspections, quality checks, audits
5. **Task management** - Work orders, maintenance, assignments
6. **Media attachments** - Photos and documents are universal needs

All patterns avoid domain-specific terms (like "tree" or "urban") and use generic names that apply to many contexts.

## Stability

All 15 entries are marked **stable** - production-ready and recommended for use.

## Comparison with Other Examples

| Feature | simple_task | support_tickets | urban_canopy |
|---------|-------------|-----------------|--------------|
| Location patterns | ❌ | ❌ | ✅ (3 entries) |
| Asset tracking | ❌ | ❌ | ✅ (3 entries) |
| Media attachments | ❌ | ❌ | ✅ (3 entries) |
| Task management | ✓ Basic | ✓ Advanced | ✓ Generic |
| Member/volunteer | ❌ | ❌ | ✅ (2 entries) |
| Observation logs | ❌ | ❌ | ✅ (1 entry) |

Urban Canopy vocabulary fills the gap for **location-based** and **asset-tracking** applications.
