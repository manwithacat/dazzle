# Dazzle Project Instructions for Claude

This is a Dazzle project for generating full-stack applications from DSL specifications.

## MCP Tools Available

You have access to the DAZZLE MCP server with consolidated tools:

- `dsl` — validate, inspect_entity, inspect_surface, lint, analyze
- `knowledge` — concept, examples, workflow, inference
- `story` — propose, save, get, generate_tests, coverage
- `bootstrap` — entry point for "build me an app" requests

## Your Primary Tasks

1. **Help write DSL specifications** in the `dsl/` directory
2. **Validate DSL** using `dazzle validate`
3. **Run the application** using `dazzle serve`
4. **Fix validation errors** by editing `.dsl` files
5. **Answer questions** about Dazzle DSL syntax and capabilities

## Project Structure

```
.
├── dazzle.toml         # Project configuration
├── SPEC.md             # Natural language requirements (optional)
├── dsl/                # DSL specification files
│   └── *.dsl          # Your domain models and UI definitions
└── .dazzle/            # Runtime state and logs (gitignored)
```

## Common Workflows

### Creating DSL from Requirements
If the user has requirements in SPEC.md or describes them to you:
1. Help them write DSL directly
2. Create entities, surfaces, and other constructs in `.dsl` files
3. Validate with `dazzle validate`
4. Run with `dazzle serve`

### Working with Existing DSL
1. Read existing `.dsl` files in the `dsl/` directory
2. Make modifications as requested
3. Always validate after changes
4. Run with `dazzle serve` to test

### Running the Application
```bash
dazzle serve              # Run with Docker (default)
dazzle serve --local      # Run without Docker
```
- UI: http://localhost:3000
- API: http://localhost:8000/docs

## DSL Quick Reference

### Multi-Module Projects
Each `.dsl` file should declare its module and import dependencies:
```dsl
module myapp.core

# Import entities from other modules
use myapp.other_module

app myapp "My Application"

entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  created_at: datetime auto_add
```

### Entity with Archetypes and Patterns
```dsl
entity Task "Task":
  intent: "Work items to track progress"
  domain: project_management
  patterns: lifecycle, audit

  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[open,in_progress,done]=open
  priority: enum[low,medium,high]=medium
  due_date: date optional
  assignee: ref User optional
```

### Surface (UI)
```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field status "Status"
    field assignee "Assigned To"
```

### Field Types
- `uuid`, `str(n)`, `text`, `int`, `decimal(p,s)`, `bool`
- `datetime`, `date`
- `email` - validated email address
- `enum[option1,option2,option3]` - enumerated values
- `ref OtherEntity` - foreign key relationship
- `has_many OtherEntity` - one-to-many relationship
- `belongs_to OtherEntity` - inverse of has_many

### Modifiers
- `pk` - Primary key
- `required` - Not nullable
- `optional` - Nullable (default)
- `unique` - Unique constraint
- `auto_add` - Set on creation
- `auto_update` - Update on save
- `=value` - Default value

### Reserved Keywords
Some words are reserved and cannot be used as enum values:
- Use `add/modify/remove` instead of `create/update/delete`
- Use `mail` instead of `email` for channel enums
- Use `sent` instead of `submitted`

Use MCP tool: `knowledge` with `operation=concept` and `term=reserved_keywords` for the full list.

## Important Reminders

1. **Always validate before running** - `dazzle validate` first
2. **Check the dsl/ directory** - DSL files go here, not in root
3. **Use module imports** - Add `use module_name` when referencing entities from other modules

## Your Capabilities

You can:
- ✅ Write and modify DSL files
- ✅ Run dazzle commands (validate, serve, lint, etc.)
- ✅ Debug validation errors
- ✅ Suggest DSL patterns and best practices

You should NOT:
- ❌ Modify runtime files in `.dazzle/` directory
- ❌ Create files outside the DSL structure without user request

Remember: Your primary role is to help users create applications using Dazzle DSL.

## Human-Led UX Testing Support

This project supports human-led UX testing workflows. You can monitor and triage feedback submitted by human testers.

### Personas

| Persona | Role | Default Workspace |
|---------|------|-------------------|
| `customer` | End user submitting support requests | my_tickets |
| `agent` | First-line support handling tickets | ticket_queue |
| `manager` | Team lead monitoring performance | agent_dashboard |

### Scenarios

| Scenario | Description |
|----------|-------------|
| `happy_path` | Normal ticket flow — submit, assign, resolve |
| `escalation` | Critical issue requiring manager attention |
| `backlog` | High volume testing with many open tickets (fixtures/backlog.json) |

### Feedback Monitoring (Mailpit)

Use the `mailpit` MCP tool during active testing:
```
mailpit operation=list_messages limit=10    # List recent feedback
mailpit operation=get_message message_id=X  # Get details
mailpit operation=search query="bug"        # Search by keyword
```

Triage: check messages → categorize (bug/feature/UX) → investigate DSL → suggest fix → delete when processed.

### Running

```bash
dazzle serve --local    # UI: localhost:3000 | API: localhost:8000/docs | Mailpit: localhost:8025
```

Enable feedback emails by setting `DAZZLE_FEEDBACK_EMAIL=dev@dazzle.local` in `.env.local`.
