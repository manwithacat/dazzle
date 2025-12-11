# DAZZLE DSL Reference Guide v0.9

Complete reference for the DAZZLE Domain-Specific Language.

## Document Structure

| File | Description |
|------|-------------|
| [01-modules.md](./01-modules.md) | Module declarations, app metadata, use statements |
| [02-entities.md](./02-entities.md) | Entity definitions, fields, types, relationships |
| [03-surfaces.md](./03-surfaces.md) | UI surfaces, sections, actions, outcomes |
| [04-workspaces.md](./04-workspaces.md) | Data-centric views with regions and aggregates |
| [05-services.md](./05-services.md) | External APIs and domain services |
| [06-integrations.md](./06-integrations.md) | API integrations, actions, syncs, mappings |
| [07-messaging.md](./07-messaging.md) | Channels, messages, templates, assets |
| [08-ux.md](./08-ux.md) | UX semantic layer, attention signals, persona variants |
| [09-scenarios.md](./09-scenarios.md) | Personas, scenarios, demo fixtures |
| [10-experiences.md](./10-experiences.md) | Multi-step user flows |

## Quick Start

A minimal DAZZLE application:

```dsl
module my_app
app todo "Todo App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool = false
  created_at: datetime auto_add

surface task_list "Task List":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field completed "Done"
```

## Syntax Conventions

- **Indentation**: 2 spaces (significant whitespace)
- **Strings**: Double quotes `"like this"`
- **Comments**: `# single line` or `''' multi-line '''`
- **Identifiers**: `snake_case` for names
- **Types**: `PascalCase` for entity/message names

## Reserved Keywords

```
module app entity surface workspace service integration experience
persona scenario demo message channel asset document template
field section action mode uses ref has_many has_one belongs_to embeds
required optional pk unique auto_add auto_update
str text int decimal bool date datetime uuid email enum
filter sort limit display aggregate source empty group_by
when on send receive create update delete
ux attention for scope purpose show hide focus defaults
true false null
```
