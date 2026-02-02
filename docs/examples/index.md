# Examples

Explore complete DAZZLE applications demonstrating various features and complexity levels.

## Example Projects

| Example | Complexity | Key Features |
|---------|------------|--------------|
| [Simple Task](simple-task.md) | Beginner | CRUD, surfaces, workspaces |
| [Contact Manager](contact-manager.md) | Beginner+ | Indexes, search, workspace layouts |
| [Support Tickets](support-tickets.md) | Intermediate | Foreign keys, entity relationships |
| [Ops Dashboard](ops-dashboard.md) | Intermediate+ | Personas, dashboards, engine hints |
| [FieldTest Hub](fieldtest-hub.md) | Advanced | Persona scoping, attention signals, multi-workspace |

## Learning Path

```
simple_task → contact_manager → support_tickets → ops_dashboard → fieldtest_hub
  (Beginner)    (Beginner+)      (Intermediate)   (Intermediate+)   (Advanced)
```

## Running Examples

All examples follow the same pattern:

```bash
cd examples/<example_name>
dazzle serve
```

This starts:

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

### Running Without Docker

```bash
dazzle serve --local
```

### Running with Hot Reload

```bash
dazzle serve --watch
```

## CI Priority Levels

Examples are tested in CI with different priority levels:

| Priority | Examples | CI Behavior |
|----------|----------|-------------|
| **P0** | simple_task, contact_manager | Blocks PRs |
| **P1** | support_tickets, ops_dashboard | Warnings only |
| **P2** | fieldtest_hub | Main branch only |

## Creating Your Own

Start a new project with:

```bash
dazzle init my_app
cd my_app
dazzle serve
```

See [Your First App](../getting-started/first-app.md) for a guided tutorial.
