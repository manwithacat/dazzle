# DAZZLE Examples

This directory contains example DAZZLE projects demonstrating various features and patterns.

## Available Examples

### 🎯 Simple Task Manager

**Location**: [`simple_task/`](simple_task/)

A minimal CRUD application demonstrating basic DAZZLE concepts.

**Features**:
- Single entity (Task)
- All four surface modes (list, view, create, edit)
- Field types: `uuid`, `str`, `text`, `bool`, `datetime`
- Field modifiers: `pk`, `required`, `auto_add`
- Default values

**Perfect for**:
- Learning DAZZLE basics
- Understanding entity/surface relationship
- First-time users

**Quick Start**:
```bash
cd simple_task
dazzle validate
dazzle build --backend openapi --out ./build
```

### 🎫 Support Ticket System

**Location**: [`support_tickets/`](support_tickets/)

A more complex application showing multi-entity relationships and real-world patterns.

**Features**:
- Multiple entities (User, Ticket, Comment)
- Entity relationships with `ref` fields
- Optional vs required relationships
- Enum fields with defaults
- Auto-timestamps (`auto_add`, `auto_update`)
- Multiple surfaces per entity
- Comprehensive field documentation

**Perfect for**:
- Understanding relationships
- Real-world application patterns
- Multi-entity designs
- Foreign key usage

**Quick Start**:
```bash
cd support_tickets
dazzle validate
dazzle build --backend openapi --out ./build
```

### 🌳 Urban Canopy - Tree Monitoring

**Location**: [`urban_canopy/`](urban_canopy/)

A real-world citizen science application for monitoring street tree health. Used as integration test for critical bug fixes.

**Features**:
- 4 entities with complex relationships (Tree, Observation, MaintenanceTask, Volunteer)
- Multiple foreign keys per entity
- Self-referential relationships
- Partial CRUD patterns (create-only observations)
- Multi-word entity names (MaintenanceTask)
- Geolocation fields (lat/lng)
- Rich enum usage (status, condition, types)
- State machine patterns (task workflow)

**Perfect for**:
- Real-world application architecture
- Complex entity relationships
- Testing partial CRUD patterns
- Multi-word entity naming
- Integration testing
- Understanding citizen science workflows

**Quick Start**:
```bash
cd urban_canopy
dazzle validate
dazzle build --stack micro
cd build/urbancanopy
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

**Special Note**: This example was instrumental in discovering and fixing two critical bugs in DAZZLE v0.1.1:
- BUG-001: Partial CRUD support (URLs for missing views)
- BUG-002: Multi-word entity view naming consistency

## Example Structure

Each example follows this structure:

```
example_name/
  dazzle.toml         # Project manifest
  dsl/                # DSL files
    app.dsl           # Main application definition
  build/              # Generated artifacts (gitignored)
  README.md           # Example-specific documentation
```

## Running Examples

### Validate

Check DSL syntax and semantics:

```bash
cd <example_directory>
dazzle validate
```

### Build

Generate artifacts (e.g., OpenAPI spec):

```bash
dazzle build --backend openapi --out ./build
```

View generated files:

```bash
cat build/openapi.yaml
```

### Validate All Examples

Run automated validation on all examples:

```bash
# From repository root
python tests/build_validation/validate_examples.py
```

This ensures all examples stay working as DAZZLE evolves.

## Learning Path

### 1. Start Simple

Begin with **Simple Task Manager**:
- Understand entities and fields
- Learn surface modes
- See how DSL becomes artifacts

### 2. Add Relationships

Move to **Support Ticket System**:
- Entity relationships with `ref`
- Optional vs required fields
- Multiple surfaces per entity
- Enum fields

### 3. Real-World Complexity

Study **Urban Canopy**:
- Multiple entities with complex relationships
- Partial CRUD patterns
- Multi-word entity names
- State machine workflows
- See how a real application is structured

### 4. Experiment

Modify the examples:
- Add new fields to entities
- Create new surfaces
- Add relationships between entities
- Try different surface modes

### 5. Build Your Own

Create your own DAZZLE project:
```bash
dazzle init my_project
cd my_project
# Edit dsl/app.dsl
dazzle validate
dazzle build --stack micro
```

## Example Patterns

### Basic Entity

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  completed: bool=false
  created_at: datetime auto_add
```

### Entity with Relationships

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  
  # Required relationship - every ticket has a creator
  created_by: ref User required
  
  # Optional relationship - tickets can be unassigned
  assigned_to: ref User
```

### Enum Fields

```dsl
entity Ticket:
  id: uuid pk
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
```

### List Surface

```dsl
surface task_list "Task List":
  uses entity Task
  mode: list
  
  section main "Tasks":
    field title "Title"
    field completed "Done"
    field created_at "Created"
```

### Create Surface

```dsl
surface task_create "Create Task":
  uses entity Task
  mode: create
  
  section main "New Task":
    field title "Title"
    field description "Description"
```

## Common Use Cases

### CRUD Application

See: `simple_task/`
- One entity
- Four surfaces (list, view, create, edit)
- Basic field types

### Multi-Entity System

See: `support_tickets/`
- Multiple related entities
- Foreign key relationships
- Optional vs required links

### Coming Soon

We're planning more examples:

- **E-commerce Store** - Products, orders, customers
- **Blog Platform** - Posts, comments, categories, tags
- **Project Manager** - Projects, tasks, milestones, team members
- **CRM System** - Contacts, companies, deals, activities
- **Inventory System** - Items, warehouses, stock movements

## Testing Your Changes

After modifying examples, validate them:

```bash
# Single example
cd simple_task
dazzle validate

# All examples (from repo root)
python tests/build_validation/validate_examples.py
```

## Contributing Examples

We welcome new examples! See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

### Good Example Characteristics

- **Focused**: Demonstrates specific features
- **Documented**: Includes README explaining concepts
- **Validated**: Passes `dazzle validate`
- **Tested**: Included in build validation
- **Realistic**: Based on real-world needs

### Creating a New Example

1. Create directory in `examples/`
2. Add `dazzle.toml` and `dsl/` files
3. Write `README.md` explaining the example
4. Validate: `dazzle validate`
5. Test: Add to build validation
6. Submit PR

## Example Templates

### Blank Project

For a minimal starting point:

```bash
dazzle init my_project --template blank
```

This creates the basic structure without example code.

## Troubleshooting

### "Module not found"

Check `dazzle.toml`:
```toml
[modules]
paths = ["./dsl"]  # Path to DSL files
```

### "Unexpected character" errors

- Remove Jinja2 template placeholders (`{{...}}`)
- Replace with actual values
- See recent commits for examples

### Validation passes but build fails

- Ensure backend is available: `dazzle backends`
- Check output directory permissions
- Review backend-specific requirements

## Questions?

- Check example `README.md` files
- See [main documentation](../docs/README.md)
- Open an [issue](https://github.com/yourusername/dazzle/issues)
- Start a [discussion](https://github.com/yourusername/dazzle/discussions)

---

**Happy coding with DAZZLE!** 🚀
