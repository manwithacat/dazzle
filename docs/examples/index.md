# Examples

Explore complete DAZZLE applications demonstrating various features and complexity levels.

## Example Projects

| Example | Complexity | Key Features |
|---------|------------|--------------|
| [Simple Task](simple-task.md) | Beginner | CRUD, surfaces, workspaces |
| [Support Tickets](support-tickets.md) | Intermediate | Foreign keys, entity relationships, audit |
| `invoice_ops` | Intermediate+ | Tenancy, approvals, processes |
| `hr_records` | Advanced | PII handling, org hierarchy |

Four examples remain; flense ship E (ADR-0057) retired the rest because the
consumer apps now exercise their constructs.

### Framework fixtures

| Fixture | Key Features |
|---------|--------------|
| `pra` | Experiences, wizards, multi-step flows |
| `rbac_validation` | Role-based access control, permissions |

## Learning Path

```
simple_task → support_tickets → invoice_ops → hr_records
  (Beginner)   (Intermediate)   (Intermediate+)  (Advanced)
```

## Running Examples

All examples follow the same pattern:

```bash
cd examples/<example_name>
dazzle serve
```

`dazzle serve` connects to the Postgres in your `DATABASE_URL` (and Redis in
`REDIS_URL`, if set) and starts:

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

### Re-validating on Change

`--watch` re-parses and lints the DSL on every save and prints the result;
restart the server to apply a valid change.

```bash
dazzle serve --watch
```

## CI Priority Levels

Examples are tested in CI with different priority levels:

| Priority | Examples | CI Behavior |
|----------|----------|-------------|
| **P0** | simple_task | Blocks PRs |
| **P1** | support_tickets, invoice_ops, hr_records | Warnings only |

## Creating Your Own

Copy `simple_task` and edit it, or run the MCP `bootstrap` tool against a `SPEC.md`:

```bash
cp -r examples/simple_task my_app
cd my_app
dazzle serve
```

See [Your First App](../getting-started/first-app.md) for a guided tutorial.
