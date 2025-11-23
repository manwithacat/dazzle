# Urban Canopy - Tree Monitoring Application

**Example Type**: Real-world integration test  
**Complexity**: Intermediate  
**Stack**: Django Micro Modular  
**Key Features**: Multi-entity relationships, enums, foreign keys, auto-timestamps

---

## Overview

Urban Canopy is a citizen science application that enables neighbourhood volunteers to monitor street tree health while helping municipal arborists triage maintenance issues efficiently. This example demonstrates DAZZLE's ability to model complex real-world applications with multiple related entities and rich business logic.

**Problem Addressed**: Most cities rely on slow, periodic tree surveys, causing early-warning signs (disease, drought, soil compaction) to be missed. Urban Canopy creates a continuous monitoring network using volunteer stewards.

---

## What This Example Demonstrates

### Entity Relationships
- **One-to-Many**: `Tree` → `Observation`, `Tree` → `MaintenanceTask`
- **Optional Foreign Keys**: `Tree` → `Steward (Volunteer)`
- **Required Foreign Keys**: `Observation` → `Tree`, `Observation` → `Observer`
- **Self-referential**: Volunteers can be assigned to tasks

### Field Types Used
- **Text**: `str(200)`, `text`
- **Enums**: Condition status, soil condition, task types, leaf condition
- **Booleans**: Active status, insect signs
- **Decimals**: Geolocation coordinates (lat/lng)
- **Foreign Keys**: `ref Entity`
- **Auto-timestamps**: `auto_add`, `auto_update`

### Surface Patterns
- **Full CRUD**: `Tree`, `Volunteer` (list, detail, create, edit)
- **Partial CRUD**: `Observation`, `MaintenanceTask` (testing bug fixes)
- **Multi-word Entities**: `MaintenanceTask` (tests consistent view naming)

### Business Logic
- Status-driven workflows (task states: Open → In Progress → Completed)
- Audit trail with timestamps
- Optional relationships (steward assignment)

---

## Entities

### Tree
Represents a street tree being monitored.

**Fields**:
- Species (required)
- Location (latitude/longitude)
- Condition status (enum: Healthy, Moderate Stress, Severe Stress, Dead)
- Soil condition (enum: Compact, Loose, Mulched, Unknown)
- Last inspection date (auto-updated)
- Steward (optional volunteer assignment)

### Observation
Health observations logged by volunteers or arborists.

**Fields**:
- Tree (required FK)
- Observer (required FK to Volunteer)
- Moisture level (enum: Low, Medium, High)
- Leaf condition (enum: Normal, Yellowing, Browning, Spotting)
- Insect signs (boolean)
- Notes (optional text)
- Submitted at (auto-timestamp)

### MaintenanceTask
Work items for tree maintenance.

**Fields**:
- Type (enum: Watering, Mulching, Pruning, Soil Aeration, Disease Inspection)
- Tree (required FK)
- Created by (required FK to Volunteer)
- Assigned to (optional FK to Volunteer)
- Status (enum: Open, In Progress, Completed, Cancelled)
- Notes (optional text)
- Created at / Updated at (auto-timestamps)

### Volunteer
Citizen stewards and municipal arborists.

**Fields**:
- Name (required)
- Email (required, unique)
- Preferred area (optional)
- Skill level (enum: Beginner, Intermediate, Trained Arborist)
- Active status (boolean)
- Joined at (auto-timestamp)

---

## User Stories

### Volunteer Workflows
1. **Claim a tree to steward** → Creates Tree with steward assignment
2. **Submit health observations** → Creates Observation linked to Tree
3. **Complete maintenance tasks** → Updates MaintenanceTask status

### Arborist Workflows
1. **View trees needing attention** → Filter Tree list by condition status
2. **Convert observations into tasks** → Create MaintenanceTask from Observation
3. **Assign tasks to volunteers** → Set assigned_to field

---

## Usage as Integration Test

This example was instrumental in discovering and fixing two critical bugs:

### BUG-001: Partial CRUD Support
- **Issue**: URL generator created routes for all CRUD operations, but view generator only created views for surfaces defined in DSL
- **Test Case**: `Observation` entity with create but no edit surface (observations are immutable)
- **Result**: Fixed - URLs only generated for defined surfaces

### BUG-002: Multi-word Entity Naming
- **Issue**: View generator used surface names for some views but entity names for others
- **Test Case**: `MaintenanceTask` entity with `task_list` surface
- **Expected**: `MaintenanceTaskListView` (not `TaskListView`)
- **Result**: Fixed - consistent entity-based naming

---

## Building This Example

```bash
# Clone or navigate to this example
cd examples/urban_canopy

# Validate the DSL
dazzle validate

# Build the application
dazzle build --stack micro

# Run the generated app
cd build/urbancanopy
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# Open in browser
open http://localhost:8000
```

---

## Generated Application Features

When built, this example generates:

### Views
- Home page with navigation
- Tree list and detail pages
- Observation creation form
- Maintenance task board (list view)
- Volunteer management pages
- Delete confirmation pages for all entities

### URLs
- RESTful URL patterns for all entities
- Proper URL ordering (create before detail)
- Only URLs for defined surfaces (respects partial CRUD)

### Models
- Django models with proper field types
- Foreign key relationships with CASCADE deletion
- Enum fields using Django's TextChoices
- Auto-timestamp fields using auto_now_add/auto_now

### Forms
- Django ModelForms for all create/edit surfaces
- Field validation
- Proper widget selection

### Templates
- Bootstrap-based responsive design
- List views with filtering
- Detail views with related object display
- Form views with validation errors

---

## Extending This Example

### Add Geolocation Features
```dsl
# In entity Tree, replace:
location_lat: decimal
location_lng: decimal

# With (future feature):
location: geo.point required
```

### Add Photo Uploads
```dsl
# In entity Observation, add:
photo: image optional
```

### Add Task Board View
```dsl
surface task_board "Task Board":
  uses entity MaintenanceTask
  mode: kanban
  group_by: status
  section card:
    field title
    field assigned_to
```

---

## Technical Notes

### Database Relationships
```
Tree (1) ←→ (N) Observation
Tree (1) ←→ (N) MaintenanceTask
Volunteer (1) ←→ (N) Tree (as steward)
Volunteer (1) ←→ (N) Observation (as observer)
Volunteer (1) ←→ (N) MaintenanceTask (as creator)
Volunteer (1) ←→ (N) MaintenanceTask (as assignee)
```

### Entity Complexity
- **Simple**: Volunteer (6 fields, no FK dependencies)
- **Moderate**: Tree (8 fields, 1 optional FK)
- **Complex**: MaintenanceTask (9 fields, 3 FKs, state machine)

### DSL Size
- **Entities**: 4
- **Surfaces**: 15
- **Total Lines**: ~200 (including comments)
- **Token Count**: ~800 tokens (highly efficient)

---

## Lessons Learned

### What Worked Well
1. **Enum fields** - Clean way to model status/choice fields
2. **Auto-timestamps** - Eliminates boilerplate
3. **Optional FKs** - Flexible relationships (e.g., unassigned tasks)
4. **Partial CRUD** - Immutable observations (create-only)

### Challenges Encountered
1. **Geolocation** - No native `geo.point` type yet (used decimal lat/lng)
2. **Photo uploads** - No `image` field type yet (excluded from DSL)
3. **Map views** - No `mode: map` yet (using list view)
4. **Kanban boards** - No `mode: kanban` yet (using list view)

### Future Enhancements (v0.2+)
- Add `mode: map` with geolocation support
- Add `mode: kanban` with status grouping
- Add `image` and `file` field types
- Add related record sections in detail views

---

## Related Examples

- **simple_task** - Beginner example with basic CRUD
- **support_tickets** - Intermediate example with state machines
- **llm_demo** - LLM integration patterns

---

## Files

- **`SPEC.md`** - Original product specification (5.7KB)
- **`dsl/app.dsl`** - Complete DSL definition (~200 lines)
- **`dazzle.toml`** - Project configuration

---

## Success Metrics

After building and testing this example:

- ✅ `dazzle validate` passes with no errors
- ✅ `dazzle build` succeeds and generates ~2,500 lines of code
- ✅ Generated app starts without errors
- ✅ All CRUD operations work as expected
- ✅ Relationships between entities function correctly
- ✅ Multi-word entity names handled properly
- ✅ Partial CRUD patterns supported

---

## Contributing

If you enhance this example (add features, improve DSL patterns, etc.), please:

1. Update the DSL in `dsl/app.dsl`
2. Update this README with new features
3. Rebuild and test: `dazzle build && cd build/urbancanopy && python manage.py check`
4. Submit a pull request with description of changes

---

**Created**: 2025-11-23  
**Last Updated**: 2025-11-23  
**DAZZLE Version**: 0.1.1  
**Status**: Production-ready example
