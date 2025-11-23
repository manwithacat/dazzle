# App-Local Vocabulary System

**Status**: Phase 1 Complete (v0.1.0)
**Last Updated**: 2025-11-23

## Overview

App-local vocabulary allows you to define reusable patterns, macros, and aliases that expand to core DAZZLE DSL. This enables:

- **DRY (Don't Repeat Yourself)**: Define common patterns once, use them everywhere
- **Abstraction**: Create domain-specific vocabulary that expresses intent clearly
- **Consistency**: Ensure repeated patterns are implemented identically
- **Productivity**: Write less DSL while generating more code

## Core Concepts

### Vocabulary Entries

A vocabulary entry is a named, parameterized template that expands to core DSL. Each entry has:

- **ID**: Unique identifier (e.g., `crud_surface_set`)
- **Kind**: Entry type (macro, alias, or pattern)
- **Scope**: Category (ui, data, workflow, auth, misc)
- **Parameters**: Inputs that customize the expansion
- **Expansion**: Template that generates core DSL using Jinja2

### @use Directive

The `@use` directive references a vocabulary entry in your DSL:

```dsl
@use entry_id(param1=value1, param2=value2)
```

During processing, the directive is replaced with the expanded core DSL.

## Quick Start

### 1. Create Vocabulary Manifest

Create `dazzle/local_vocab/manifest.yml`:

```yaml
version: 1.0.0
app_id: my_app
dsl_core_version: 1.0.0

entries:
  - id: timestamped_entity
    kind: macro
    scope: data
    dsl_core_version: 1.0.0
    description: Entity with created_at and updated_at timestamp fields
    parameters:
      - name: entity_name
        type: string
        required: true
    expansion:
      language: dazzle-core-dsl
      body: |
        entity {{ entity_name }} "{{ entity_name }}":
          created_at: datetime auto_add
          updated_at: datetime auto_update
    metadata:
      stability: experimental
      source: agent
    tags:
      - timestamp
      - audit
```

### 2. Use in DSL

Reference vocabulary in your DSL files:

```dsl
module my_app.core

app my_app "My Application"

# Use vocabulary to add timestamp fields
@use timestamped_entity(entity_name=Task)
  # Add custom fields after the macro
  id: uuid pk
  title: str(200) required
  description: text
```

### 3. Validate and Build

The @use directives are automatically expanded during validation and build:

```bash
dazzle validate
# OK: spec is valid.

dazzle build
# ✓ Build complete: django_micro_modular
```

## Vocabulary Management

### List Entries

```bash
# List all vocabulary entries
dazzle vocab list

# Filter by scope
dazzle vocab list --scope ui

# Filter by kind
dazzle vocab list --kind pattern

# Filter by tag
dazzle vocab list --tag crud
```

### Show Entry Details

```bash
# Show entry details and expansion
dazzle vocab show crud_surface_set

# Show without expansion template
dazzle vocab show crud_surface_set --no-expansion
```

### Expand DSL File

```bash
# Show expanded DSL (stdout)
dazzle vocab expand dsl/app.dsl

# Write expanded DSL to file
dazzle vocab expand dsl/app.dsl --output dsl/app.expanded.dsl
```

## Vocabulary Entry Schema

### Complete Entry Structure

```yaml
- id: entry_id                # Unique identifier (snake_case)
  kind: macro                 # macro | alias | pattern
  scope: ui                   # ui | data | workflow | auth | misc
  dsl_core_version: 1.0.0     # Target DSL version
  description: "..."          # Human-readable description

  parameters:                 # Parameter definitions
    - name: param_name
      type: string            # string | boolean | number | list | dict | model_ref
      required: true          # or false
      default: null           # Default value if not required
      description: "..."      # Parameter description

  expansion:                  # Expansion template
    language: dazzle-core-dsl # Always dazzle-core-dsl
    body: |
      # Jinja2 template using {{ param_name }}
      entity {{ entity_name }}:
        field: type

  metadata:                   # Additional metadata
    stability: experimental   # experimental | stable | deprecated
    source: agent             # agent | human
    created_at: ISO-8601
    usage_count: 0

  tags:                       # Tags for categorization
    - tag1
    - tag2
```

### Parameter Types

| Type | Description | Example Values |
|------|-------------|----------------|
| `string` | Text value | `"Task"`, `title` |
| `boolean` | True/false | `true`, `false` |
| `number` | Integer or float | `42`, `3.14` |
| `list` | Array of values | `[1, 2, 3]` |
| `dict` | Key-value pairs | `{key: value}` |
| `model_ref` | Entity reference | `User`, `Task` |

### Entry Kinds

| Kind | Purpose | Example |
|------|---------|---------|
| `macro` | Reusable DSL fragment with parameters | Timestamped entity fields |
| `alias` | Shorthand for common patterns | User reference field |
| `pattern` | Complex multi-construct template | Complete CRUD surface set |

### Entry Scopes

| Scope | Category | Examples |
|-------|----------|----------|
| `ui` | User interface patterns | Surfaces, forms, dashboards |
| `data` | Data model patterns | Entities, fields, constraints |
| `workflow` | Process patterns | Experiences, transitions |
| `auth` | Authentication patterns | Login, permissions |
| `misc` | Other patterns | Integrations, tests |

## @use Directive Syntax

### Basic Usage

```dsl
@use entry_id(param=value)
```

### Multiple Parameters

```dsl
@use entry_id(
  param1=value1,
  param2=value2,
  param3=value3
)
```

### Parameter Value Types

```dsl
# String (quoted or unquoted)
@use entry(name="Task")
@use entry(name=Task)

# Boolean
@use entry(enabled=true)
@use entry(required=false)

# Number
@use entry(count=42)
@use entry(ratio=3.14)

# List
@use entry(items=[1, 2, 3])
@use entry(names=["Alice", "Bob"])
```

## Example Vocabulary Entries

### Simple Alias: User Reference

```yaml
- id: user_reference
  kind: alias
  scope: data
  dsl_core_version: 1.0.0
  description: Standard user reference field
  parameters:
    - name: field_name
      type: string
      required: false
      default: user
  expansion:
    language: dazzle-core-dsl
    body: "{{ field_name }}: ref User"
  metadata:
    stability: experimental
  tags: [reference, user, data]
```

Usage:
```dsl
entity Task "Task":
  @use user_reference(field_name=assigned_to)
```

Expands to:
```dsl
entity Task "Task":
  assigned_to: ref User
```

### Pattern: CRUD Surface Set

```yaml
- id: crud_surface_set
  kind: pattern
  scope: ui
  dsl_core_version: 1.0.0
  description: Complete CRUD surface set (list, detail, create, edit)
  parameters:
    - name: entity_name
      type: string
      required: true
    - name: title_field
      type: string
      required: true
  expansion:
    language: dazzle-core-dsl
    body: |
      surface {{ entity_name }}_list "{{ entity_name }} List":
        uses entity {{ entity_name }}
        mode: list
        section main "{{ entity_name }}s":
          field {{ title_field }} "{{ title_field | title }}"

      surface {{ entity_name }}_detail "{{ entity_name }} Detail":
        uses entity {{ entity_name }}
        mode: view
        section main "{{ entity_name }} Details":
          field {{ title_field }} "{{ title_field | title }}"

      surface {{ entity_name }}_create "Create {{ entity_name }}":
        uses entity {{ entity_name }}
        mode: create
        section main "New {{ entity_name }}":
          field {{ title_field }} "{{ title_field | title }}"

      surface {{ entity_name }}_edit "Edit {{ entity_name }}":
        uses entity {{ entity_name }}
        mode: edit
        section main "Edit {{ entity_name }}":
          field {{ title_field }} "{{ title_field | title }}"
  metadata:
    stability: experimental
  tags: [crud, ui, pattern]
```

Usage:
```dsl
@use crud_surface_set(entity_name=Task, title_field=title)
```

Expands to 4 surfaces: task_list, task_detail, task_create, task_edit

## Best Practices

### 1. Keep Expansions Simple

✅ **Good**: Single responsibility, clear purpose
```yaml
- id: user_reference
  expansion:
    body: "{{ field_name }}: ref User"
```

❌ **Bad**: Too complex, multiple responsibilities
```yaml
- id: everything
  expansion:
    body: |
      # Hundreds of lines of DSL...
```

### 2. Use Descriptive IDs

✅ **Good**: Clear, self-documenting
```yaml
- id: timestamped_entity
- id: crud_surface_set
- id: user_reference_field
```

❌ **Bad**: Cryptic abbreviations
```yaml
- id: te
- id: css
- id: urf
```

### 3. Provide Good Descriptions

✅ **Good**: Explains what and why
```yaml
description: "Entity with created_at and updated_at timestamp fields for audit tracking"
```

❌ **Bad**: Vague or missing
```yaml
description: "Entity with fields"
```

### 4. Use Appropriate Scopes

Match the scope to the entry's primary purpose:
- `ui` - Surfaces, forms, dashboards
- `data` - Entities, fields, relationships
- `workflow` - Experiences, state machines
- `auth` - Authentication, authorization
- `misc` - Everything else

### 5. Tag Effectively

Add tags that help find related entries:
```yaml
tags:
  - crud        # Functionality
  - ui          # Category
  - admin       # Context
  - common      # Frequency
```

### 6. Version Your Vocabulary

Update `metadata.stability` as entries mature:
- `experimental` - New, may change
- `stable` - Mature, reliable
- `deprecated` - Use alternatives

### 7. Don't Nest @use Directives

❌ **Bad**: Nested @use (not supported)
```dsl
@use outer(
  content="@use inner(param=value)"
)
```

✅ **Good**: Flat @use directives
```dsl
@use entry1(param=value)
@use entry2(param=value)
```

## Integration with Build Pipeline

The vocabulary expander is automatically integrated into the DAZZLE build pipeline:

1. **Parse Phase**: DSL files are read
2. **Expand Phase**: @use directives are expanded to core DSL
3. **Validate Phase**: Expanded DSL is validated
4. **Link Phase**: Modules are linked
5. **Generate Phase**: Code is generated

This means vocabulary expansion is:
- **Transparent**: Works with all existing commands
- **Automatic**: No manual expansion needed
- **Safe**: Errors are caught during validation

## Limitations (Phase 1)

Current limitations (will be addressed in future phases):

1. **No Nested Expansion**: @use directives cannot be nested
2. **No Cross-Module References**: Vocabulary is per-app only
3. **Manual Creation**: Entries must be created manually
4. **No Extension Packs**: Can't share vocabulary across apps (yet)
5. **No Pattern Detection**: No automatic identification of repeated patterns (yet)

## Complete Example

See `examples/vocab_demo/` for a working example:

```bash
cd examples/vocab_demo
dazzle vocab list
dazzle vocab show crud_surface_set
dazzle vocab expand dsl/app.dsl
dazzle validate
dazzle build --stack openapi
```

## Next Steps

**Phase 2** (Planned):
- Automatic pattern detection in existing DSL
- Vocabulary suggestion engine
- Cross-module vocabulary references

**Phase 3** (Planned):
- Extension packs (shareable vocabulary bundles)
- Vocabulary mining across projects
- Community vocabulary marketplace

**Phase 4** (Planned):
- LLM-assisted vocabulary creation
- Automatic vocabulary optimization
- Smart vocabulary recommendations

## See Also

- [DAZZLE DSL Reference](DAZZLE_DSL_REFERENCE_0_1.md) - Core DSL syntax
- [Architecture Spec](../dev_docs/architecture/dazzle_app_local_vocab_spec_v1.md) - Technical specification
- [Evaluation](../dev_docs/architecture/app_local_vocab_evaluation.md) - Implementation roadmap
