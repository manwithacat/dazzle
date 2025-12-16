# Examples

Explore complete DAZZLE applications demonstrating various features and complexity levels.

## Example Projects

| Example | Complexity | Key Features |
|---------|------------|--------------|
| [Simple Task](simple-task.md) | Beginner | CRUD, surfaces, workspaces |
| [Contact Manager](contact-manager.md) | Beginner | Relationships, search |
| [Ops Dashboard](ops-dashboard.md) | Intermediate | Dashboards, metrics, charts |
| [Email Client](email-client.md) | Intermediate | Messaging, threads |
| [Uptime Monitor](uptime-monitor.md) | Intermediate | Services, integrations, scenarios |
| [Inventory Scanner](inventory-scanner.md) | Advanced | Experiences, state machines |

## Running Examples

All examples follow the same pattern:

```bash
cd examples/<example_name>
dazzle dnr serve
```

This starts:

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

### Running Without Docker

```bash
dazzle dnr serve --local
```

### Running with Hot Reload

```bash
dazzle dnr serve --watch
```

## CI Priority Levels

Examples are tested in CI with different priority levels:

| Priority | Examples | CI Behavior |
|----------|----------|-------------|
| **P0** | simple_task, contact_manager | Blocks PRs |
| **P1** | ops_dashboard, email_client | Warnings only |
| **P2** | uptime_monitor, inventory_scanner | Main branch only |

## Creating Your Own

Start a new project with:

```bash
dazzle init my_app
cd my_app
dazzle dnr serve
```

See [Your First App](../getting-started/first-app.md) for a guided tutorial.
