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

Check your DSL for parse, link, and semantic errors:

```bash
dazzle validate
```

Expected output:

```
Validating my_tasks...
✓ 1 module, 1 entity, 4 surfaces, 1 workspace
All valid!
```

Validation is the first trust boundary: Dazzle has parsed the DSL into an AppSpec, resolved references, and confirmed that the surfaces point at real entities and fields.

## Step 6: Inspect What Dazzle Understood

Before running the app, inspect the model Dazzle derived from your DSL:

```bash
dazzle inspect project --entity Task
dazzle specs openapi -f json
```

The first command shows the entity as Dazzle sees it after parsing and linking. The second emits the OpenAPI contract derived from the same AppSpec. This is the basic cause-and-effect loop: edit DSL, validate, inspect the derived model, then run.

For apps with personas and access rules, also run:

```bash
dazzle rbac matrix --format table
```

This tutorial app has no access-control rules yet, so any `PERMIT_UNPROTECTED` output is expected. In a real app, treat that as a finding to fix before production.

## Step 7: Run

Start the development server:

```bash
dazzle serve
```

Open your browser:

- **UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

## Step 8: Test the API

Try creating a task via the API:

```bash
curl -X POST http://localhost:8000/_dazzle/tasks \
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
- Add [personas and access rules](../reference/access-control.md), then review the RBAC matrix
- Organize role-specific dashboards with [workspaces](../reference/workspaces.md)
- Set up [services](../reference/services.md) for business logic
- Follow the [skeptical evaluation guide](../evaluation/evaluation.md) to verify RBAC, compliance evidence, and runtime behavior
- Explore [examples](../examples/index.md) for more complex patterns

## Troubleshooting

### "Port already in use"

```bash
dazzle serve --port 3001
```

### Validation errors

```bash
dazzle validate --verbose
```

### Need help?

```bash
dazzle --help
```
