# DAZZLE Examples

This directory contains example DAZZLE projects demonstrating various features.

## Examples

### 1. Simple Task Manager (`simple_task/`)

A minimal task management application demonstrating basic DAZZLE concepts:
- Single entity (Task)
- CRUD surfaces (list, view, create, edit)
- Enum fields and datetime fields

**Run**:
```bash
cd examples/simple_task
dazzle validate
dazzle build --backend openapi --out ./build
```

### 2. Support Ticket System (`support_tickets/`)

A more complex example with:
- Multiple entities (User, Ticket, Comment)
- Multi-module structure (auth + core)
- Cross-module references
- Entity relationships
- Services and integrations
- Experiences (multi-step workflows)

**Run**:
```bash
cd examples/support_tickets
dazzle validate
dazzle lint --strict
dazzle build --backend openapi --out ./build
```

## Structure

Each example is a complete DAZZLE project with:
- `dazzle.toml` - Project manifest
- `dsl/` - DSL module files
- `build/` - Generated output (created after running `dazzle build`)

## Learning Path

1. **Start with Simple Task**: Understand basic entities and surfaces
2. **Explore Support Tickets**: Learn multi-module projects and integrations
3. **Create Your Own**: Use these as templates for your applications

## Documentation

See the main [DAZZLE documentation](../README.md) for:
- DSL reference
- CLI commands
- Backend options
- Best practices
