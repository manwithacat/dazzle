# DSL Reference

Complete reference for the DAZZLE Domain-Specific Language v0.24.

## Reference Documents

| Section | Description |
|---------|-------------|
| [Modules](modules.md) | Module declarations, app metadata, use statements |
| [Entities](entities.md) | Entity definitions, fields, types, relationships |
| [Surfaces](surfaces.md) | UI surfaces, sections, actions, outcomes |
| [Workspaces](workspaces.md) | Data-centric views with regions and aggregates |
| [Services](services.md) | External APIs and domain services |
| [Integrations](integrations.md) | API integrations, actions, syncs, mappings |
| [Ledgers](ledgers.md) | TigerBeetle ledgers and transactions for accounting |
| [Messaging](messaging.md) | Channels, messages, templates, assets |
| [UX Layer](ux.md) | UX semantic layer, attention signals, persona variants |
| [Scenarios](scenarios.md) | Personas, scenarios, demo fixtures |
| [Experiences](experiences.md) | Multi-step user flows |
| [CLI](cli.md) | Command-line interface reference |
| [Grammar](grammar.md) | Formal EBNF grammar specification |

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
ledger transaction transfer debit credit amount
account_code ledger_id account_type currency flags
sync_to idempotency_key validation execution priority
asset liability equity revenue expense
true false null
```
