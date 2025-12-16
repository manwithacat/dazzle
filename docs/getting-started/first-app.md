# Your First App

Build a complete task manager from scratch in 10 minutes.

## Prerequisites

- Dazzle installed ([Installation Guide](installation.md))
- A terminal

## Step 1: Create Project

```bash
dazzle init my_tasks
cd my_tasks
```

This creates:

```
my_tasks/
├── dazzle.toml          # Project configuration
└── dsl/
    └── app.dsl          # Main DSL file
```

## Step 2: Define Your Entity

Open `dsl/app.dsl` and add a Task entity:

```dsl
module my_tasks
app my_tasks "My Tasks"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo, in_progress, done] = todo
  priority: enum[low, medium, high] = medium
  due_date: date
  created_at: datetime auto_add
```

### Understanding the DSL

| Element | Meaning |
|---------|---------|
| `entity Task` | Defines a data model |
| `id: uuid pk` | UUID primary key |
| `str(200)` | String with max 200 chars |
| `required` | Field cannot be null |
| `enum[...]` | Enumeration type |
| `= todo` | Default value |
| `auto_add` | Automatically set on creation |

## Step 3: Add Surfaces

Surfaces define how users interact with entities:

```dsl
surface task_list "Task List" -> Task list:
  section main:
    field title "Title"
    field status "Status"
    field priority "Priority"
    field due_date "Due"

surface task_detail "Task Detail" -> Task view:
  section header:
    field title "Title"
    field status "Status"
  section content:
    field description "Description"
    field priority "Priority"
    field due_date "Due Date"
    field created_at "Created"

surface task_create "New Task" -> Task create:
  section main:
    field title "Title" required
    field description "Description"
    field priority "Priority"
    field due_date "Due Date"

surface task_edit "Edit Task" -> Task edit:
  section main:
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
```

### Surface Modes

| Mode | Purpose |
|------|---------|
| `list` | Display multiple records |
| `view` | Display single record (read-only) |
| `create` | Form for new records |
| `edit` | Form for updating records |

## Step 4: Create Workspace

Workspaces organize surfaces into a layout:

```dsl
workspace dashboard "Dashboard":
  region main:
    surface task_list
  region panel:
    surface task_detail
```

## Step 5: Validate

Check your DSL for errors:

```bash
dazzle validate
```

Expected output:

```
Validating my_tasks...
✓ 1 module, 1 entity, 4 surfaces, 1 workspace
All valid!
```

## Step 6: Run

Start the development server:

```bash
dazzle dnr serve
```

Open your browser:

- **UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

## Step 7: Test the API

Try creating a task via the API:

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Learn Dazzle", "priority": "high"}'
```

## Complete DSL

Here's the full `app.dsl`:

```dsl
module my_tasks
app my_tasks "My Tasks"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo, in_progress, done] = todo
  priority: enum[low, medium, high] = medium
  due_date: date
  created_at: datetime auto_add

surface task_list "Task List" -> Task list:
  section main:
    field title "Title"
    field status "Status"
    field priority "Priority"
    field due_date "Due"

surface task_detail "Task Detail" -> Task view:
  section header:
    field title "Title"
    field status "Status"
  section content:
    field description "Description"
    field priority "Priority"
    field due_date "Due Date"
    field created_at "Created"

surface task_create "New Task" -> Task create:
  section main:
    field title "Title" required
    field description "Description"
    field priority "Priority"
    field due_date "Due Date"

surface task_edit "Edit Task" -> Task edit:
  section main:
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"

workspace dashboard "Dashboard":
  region main:
    surface task_list
  region panel:
    surface task_detail
```

## Next Steps

- Add [relationships](../reference/entities.md) between entities
- Create [personas](../reference/workspaces.md) for different user roles
- Set up [services](../reference/services.md) for business logic
- Explore [examples](../examples/index.md) for more complex patterns

## Troubleshooting

### "Port already in use"

```bash
dazzle dnr serve --port 3001
```

### Validation errors

```bash
dazzle validate --verbose
```

### Need help?

```bash
dazzle --help
```
