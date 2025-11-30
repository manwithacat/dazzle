# Simple Task Manager

A minimal DAZZLE example demonstrating core DSL concepts and CRUD patterns.

## What This Example Demonstrates

### Entity Basics
- **Primary keys**: `uuid pk` for unique identifiers
- **Field types**: `str`, `text`, `enum`, `date`, `datetime`
- **Constraints**: `required`, field length limits (e.g., `str(200)`)
- **Defaults**: `=todo`, `=medium` for enum fields
- **Auto-fields**: `auto_add`, `auto_update` for timestamps

### Surface Patterns
- **List surface**: Overview table with filtering/sorting
- **Detail surface**: Individual record view
- **Create surface**: New record form
- **Edit surface**: Update existing record form

### DSL Best Practices Demonstrated

1. **Consistent enum casing**: Use lowercase with underscores
   ```dsl
   status: enum[todo,in_progress,done]=todo
   ```

2. **Required vs optional fields**:
   - Required: `title: str(200) required`
   - Optional: `description: text` (no required keyword)
   - Optional with default: `status: enum[todo,in_progress,done]=todo`

3. **Auto-generated fields**:
   ```dsl
   created_at: datetime auto_add    # Set once on creation
   updated_at: datetime auto_update  # Updated on every change
   ```

4. **Complete CRUD**: Always include all four surfaces (list, detail, create, edit) for each entity

## Quick Start

### With Next.js (recommended)
```bash
cd /path/to/dazzle/examples/simple_task
dazzle build --stack nextjs_onebox
cd build/simple_task
npm install
npm run db:generate
npm run db:push
npm run dev
```

Open http://localhost:3000

### With Django
```bash
cd /path/to/dazzle/examples/simple_task
dazzle build --stack django_micro
cd build/simple_task
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://localhost:8000

## Project Structure

```
simple_task/
├── dazzle.toml          # Project configuration
└── dsl/
    └── app.dsl          # Application specification
```

## The DSL

### Entity Definition
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  due_date: date
  assigned_to: str(100)
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

### Surface Definitions
```dsl
# List all tasks
surface task_list "Task List":
  uses entity Task
  mode: list
  section main "Tasks":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"

# View one task
surface task_detail "Task Detail":
  uses entity Task
  mode: view
  # ... fields ...

# Create new task
surface task_create "Create Task":
  uses entity Task
  mode: create
  # ... fields ...

# Edit existing task
surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  # ... fields ...
```

## Common Patterns

### Field Types Reference
- `str(N)` - String with max length N
- `text` - Unlimited text
- `int` - Integer number
- `bool` - True/false
- `date` - Date only (YYYY-MM-DD)
- `datetime` - Date and time
- `uuid` - Unique identifier (auto-generated)
- `enum[a,b,c]` - Enumerated values (dropdown)

### Field Modifiers
- `required` - Field must have a value
- `pk` - Primary key (unique identifier)
- `unique` - Value must be unique across all records
- `auto_add` - Set automatically when created
- `auto_update` - Updated automatically when saved
- `=value` - Default value

### Surface Modes
- `list` - Table/grid view of multiple records
- `view` - Read-only detail view of one record
- `create` - Form to create new record
- `edit` - Form to update existing record

## Try Modifying

### Add a New Field

1. **Add to entity**:
```dsl
entity Task "Task":
  # ... existing fields ...
  tags: str(200)  # Add this
```

2. **Add to surfaces** (in create and edit forms):
```dsl
surface task_create "Create Task":
  section main "New Task":
    # ... existing fields ...
    field tags "Tags"  # Add this
```

3. **Rebuild**:
```bash
dazzle build --stack nextjs_onebox
```

### Change Enum Values

```dsl
# Before
status: enum[todo,in_progress,done]=todo

# After - add more statuses
status: enum[backlog,todo,in_progress,blocked,done]=backlog
```

Remember to update the default value if needed!

## Learning Path

1. **Start here** - Understand the basic entity and surface definitions
2. **Modify fields** - Add new fields or change existing ones
3. **Try different stacks** - Build with Django, Express, Next.js
4. **Move to support_tickets** - See multi-entity relationships

## Key Files in Generated Code

### Next.js Stack
```
build/simple_task/
├── package.json                       # Dependencies
├── prisma/
│   └── schema.prisma                  # Database schema (from entities)
├── src/
│   ├── app/
│   │   ├── task_list/page.tsx        # List view (from task_list surface)
│   │   ├── tasks/
│   │   │   ├── [id]/page.tsx         # Detail view (from task_detail)
│   │   │   ├── [id]/edit/page.tsx    # Edit form (from task_edit)
│   │   │   └── new/page.tsx          # Create form (from task_create)
│   ├── actions/
│   │   └── task.ts                    # Server actions (CRUD operations)
│   ├── types/
│   │   └── entities.ts                # TypeScript types (from entities)
│   └── components/                    # UI components
```

### Django Stack
```
build/simple_task/
├── manage.py
├── requirements.txt
├── app/
│   ├── models.py                      # Task model (from entity)
│   ├── forms.py                       # Task forms (from surfaces)
│   ├── views.py                       # CRUD views (from surfaces)
│   └── templates/                     # HTML templates
└── static/                            # CSS, images
```

## Next Steps

After mastering this example:
- **support_tickets** - Multi-entity relationships with foreign keys
- **Create your own** - `dazzle init my-app`
- **Explore other stacks** - Try Django API, Express, OpenAPI

## Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### List View with Data
![List View](screenshots/14_list_view_data.png)

### Create Form
![Create Form](screenshots/05_create_form_no_inputs.png)

## Getting Help

- Documentation: `docs/` in the DAZZLE repository
- Issues: https://github.com/manwithacat/dazzle/issues
- DSL Reference: `docs/DAZZLE_DSL_REFERENCE_0_1.md`
