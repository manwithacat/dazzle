# Dazzle Vocabulary Guide

**Version**: 0.2.0
**Status**: Stable

## What is Vocabulary?

Vocabulary is Dazzle's **macro system** - reusable patterns that expand to core DSL. Think of it as "DSL shortcuts" that let you express common patterns concisely.

```dsl
# Instead of writing 50 lines of DSL for auth...
@use simple_auth()

# ...you get User, Session entities, and auth endpoints automatically
```

## What Vocabulary IS For

### 1. Eliminating Repetition

When you find yourself writing similar DSL patterns repeatedly, create a vocabulary entry:

```yaml
# Before: Copy-paste these 3 fields to every entity
entity Task:
  created_at: datetime auto_add
  updated_at: datetime auto_update
  created_by: ref User

entity Project:
  created_at: datetime auto_add
  updated_at: datetime auto_update
  created_by: ref User

# After: Define once, use everywhere
@use audit_fields()
```

### 2. Encoding Domain Patterns

Capture your domain's common patterns as vocabulary:

```yaml
# E-commerce: Every order needs status tracking
- id: order_status_fields
  expansion: |
    status: enum[pending,processing,shipped,delivered,cancelled]=pending
    status_changed_at: datetime
    status_changed_by: ref User

# SaaS: Every entity needs tenant isolation
- id: tenant_scoped
  expansion: |
    tenant: ref Organization required
```

### 3. Standardizing Conventions

Enforce team conventions through vocabulary:

```yaml
# All entities use UUID primary keys
- id: standard_pk
  expansion: "id: uuid pk"

# All user-facing titles have consistent length
- id: title_field
  parameters:
    - name: max_length
      default: 200
  expansion: "title: str({{ max_length }}) required"
```

### 4. Bootstrapping Common Features

Get started quickly with pre-built patterns:

```dsl
# Full authentication system
@use simple_auth()

# Complete CRUD surfaces for an entity
@use crud_surface_set(entity_name=Product, title_field=name)

# Standard ticket/issue tracking entity
@use ticket_entity()
```

### 5. Cross-Stack Intent

Express *what* you want without specifying *how*:

```yaml
# "I want soft delete" - stack decides implementation
- id: soft_delete
  hints:
    django: Custom manager with is_deleted filter
    fastapi: Query dependency to exclude deleted
    graphql: Filter in dataloader
  expansion: |
    deleted_at: datetime optional
    deleted_by: ref User
```

## What Vocabulary is NOT For

### 1. NOT for Business Logic

Vocabulary expands to DSL structure, not runtime behavior:

```yaml
# BAD: Trying to encode logic in vocabulary
- id: calculate_total
  expansion: |
    # This won't work - DSL doesn't have calculations
    total = sum(line_items.price * line_items.quantity)

# GOOD: Define the structure, implement logic elsewhere
- id: order_totals
  expansion: |
    subtotal: decimal(10,2)
    tax: decimal(10,2)
    total: decimal(10,2)
```

### 2. NOT for One-Off Customizations

If you'll only use it once, just write the DSL:

```yaml
# BAD: Vocabulary for a single use case
- id: my_specific_user_entity
  expansion: |
    entity MyAppUser "User":
      # ... 20 very specific fields

# GOOD: Just write the entity directly in your DSL
entity MyAppUser "User":
  # ... your specific fields
```

### 3. NOT for Complex Conditional Logic

Vocabulary templates are simple - don't try to encode complex branching:

```yaml
# BAD: Too much conditional complexity
- id: overly_complex
  expansion: |
    {% if feature_a and not feature_b %}
      {% if mode == 'advanced' %}
        {% for item in complex_list %}
          ...
        {% endfor %}
      {% endif %}
    {% endif %}

# GOOD: Simple, composable entries
- id: simple_audit
  expansion: |
    created_at: datetime auto_add
    updated_at: datetime auto_update

- id: with_author
  expansion: |
    @use simple_audit()
    created_by: ref User required
```

### 4. NOT for Runtime Configuration

Vocabulary is compile-time expansion, not runtime configuration:

```yaml
# BAD: Trying to do runtime config
- id: feature_flag
  expansion: |
    # This won't check flags at runtime
    {% if FEATURE_ENABLED %}show_field: bool{% endif %}

# GOOD: Use dazzle.toml for runtime config
# dazzle.toml:
[features]
show_advanced = true
```

### 5. NOT for Replacing Core DSL

Vocabulary extends DSL, it doesn't replace fundamental concepts:

```yaml
# BAD: Reimplementing core DSL features
- id: my_entity
  kind: pattern
  expansion: |
    # Don't reinvent entity syntax
    define_model {{ name }} with fields {{ fields }}

# GOOD: Use DSL naturally, vocabulary adds conveniences
entity Task "Task":
  @use standard_pk()
  title: str(200) required
  @use audit_fields()
```

## Vocabulary Architecture

### Entry Kinds

| Kind | Purpose | Example |
|------|---------|---------|
| `macro` | Inline field/content expansion | `@use audit_fields()` → adds timestamp fields |
| `alias` | Shorthand for common patterns | `@use user_ref(field=owner)` → `owner: ref User` |
| `pattern` | Multi-construct generation | `@use crud_surfaces(entity=Task)` → 4 surfaces |

### Entry Scopes

| Scope | Category | Examples |
|-------|----------|----------|
| `data` | Entity fields, types | `audit_fields`, `soft_delete`, `tenant_scoped` |
| `ui` | Surfaces, forms | `crud_surface_set`, `list_surface`, `detail_view` |
| `workflow` | Experiences, flows | `approval_workflow`, `ticket_lifecycle` |
| `auth` | Authentication | `simple_auth`, `jwt_auth`, `role_based_access` |
| `misc` | Everything else | `api_key`, `webhook_config` |

### Expansion Process

```
DSL File                    Vocabulary Manifest           Expanded DSL
─────────                   ──────────────────           ────────────

entity Task:           ┌──▶ - id: audit_fields    ──┐    entity Task:
  id: uuid pk          │     expansion: |           │      id: uuid pk
  title: str(200)      │       created_at: ...     │      title: str(200)
  @use audit_fields() ─┘       updated_at: ...    ─┴──▶   created_at: datetime auto_add
                                                          updated_at: datetime auto_update
```

## Standard Library (stdlib)

Dazzle includes a standard library of vocabulary entries:

### Auth (`@use simple_auth()`, `@use jwt_auth()`)

Complete authentication systems:

```dsl
# Session-based auth (default)
@use simple_auth()

# JWT for APIs
@use jwt_auth(access_token_minutes=30)

# Add role-based access
@use role_based_access()
```

### Data Patterns

```dsl
# Timestamp fields
@use audit_fields()

# Soft delete support
@use soft_delete()

# Multi-tenant isolation
@use tenant_scoped(tenant_entity=Organization)

# Standard status workflow
@use status_workflow(states=[draft,review,published])
```

### UI Patterns

```dsl
# Generate all CRUD surfaces
@use crud_surface_set(entity_name=Product, title_field=name)

# Just a list view
@use list_surface(entity_name=Order, display_field=order_number)
```

## Creating Custom Vocabulary

### File Structure

```
your_project/
├── dazzle.toml
├── dsl/
│   └── app.dsl
└── dazzle/
    └── local_vocab/
        ├── manifest.yml      # Your vocabulary entries
        └── README.md         # Documentation
```

### Manifest Format

```yaml
version: 1.0.0
app_id: your_app
dsl_core_version: 1.0.0

entries:
  - id: entry_name           # snake_case identifier
    kind: macro              # macro | alias | pattern
    scope: data              # data | ui | workflow | auth | misc
    description: "What this does"

    parameters:              # Optional inputs
      - name: param_name
        type: string         # string | boolean | number | list
        required: false
        default: "default_value"

    expansion:
      language: dazzle-core-dsl
      body: |
        # Jinja2 template
        field_name: type {{ param_name }}

    metadata:
      stability: stable      # experimental | stable | deprecated
      source: human          # human | agent

    tags:
      - category
      - feature
```

### Template Syntax

Vocabulary uses Jinja2 templates:

```yaml
expansion:
  body: |
    # Variable substitution
    name: str({{ max_length }})

    # Conditionals
    {% if include_timestamps %}
    created_at: datetime auto_add
    {% endif %}

    # Loops
    {% for field in extra_fields %}
    {{ field.name }}: {{ field.type }}
    {% endfor %}

    # Filters
    {{ entity_name | lower }}_list  # task_list
    {{ name | title }}              # My Name
```

## Best Practices

### DO

1. **Keep expansions focused** - One entry, one purpose
2. **Use descriptive IDs** - `soft_delete_with_audit` not `sd1`
3. **Document parameters** - Future you will thank you
4. **Test expansions** - `dazzle vocab expand` to verify
5. **Version carefully** - Changing entries affects all uses

### DON'T

1. **Don't nest @use** - Entries can't contain @use directives
2. **Don't over-parameterize** - If you need 10 parameters, reconsider
3. **Don't encode secrets** - Never put credentials in vocabulary
4. **Don't duplicate stdlib** - Check standard library first
5. **Don't create single-use entries** - Just write the DSL

## Commands

```bash
# List all vocabulary entries
dazzle vocab list

# Filter by scope or kind
dazzle vocab list --scope auth
dazzle vocab list --kind pattern

# Show entry details
dazzle vocab show simple_auth

# Preview expansion
dazzle vocab expand dsl/app.dsl

# Validate vocabulary syntax
dazzle vocab validate
```

## See Also

- [DSL Reference](DAZZLE_DSL_REFERENCE.md) - Core DSL syntax
- [Auth Vocabulary](../../src/dazzle/stdlib/auth_vocab.yml) - Standard auth patterns
- [Example Vocabulary](../../examples/simple_task/dazzle/local_vocab/manifest.yml) - Project examples
