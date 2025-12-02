# DAZZLE DSL Quick Reference

**Learn the syntax in 5 minutes.** This guide covers every field type, surface mode, and common pattern with working examples.

---

## Table of Contents

1. [Field Types & Syntax](#field-types--syntax)
2. [Default Values](#default-values)
3. [Surface Modes](#surface-modes)
4. [Relationships](#relationships)
5. [Common Patterns](#common-patterns)
6. [Reserved Keywords](#reserved-keywords)
7. [Gotchas & Solutions](#gotchas--solutions)

---

## Field Types & Syntax

### Basic Types

```dsl
# String fields
name: str(200) required          # Max 200 chars, required
bio: text optional               # Long text, optional
slug: str(100) unique            # Unique constraint

# Numbers
age: int required                # Integer
price: decimal(10,2) required    # Decimal (precision, scale)
rating: float optional           # Floating point

# Booleans
is_active: bool                  # True/False
is_verified: bool required       # Required boolean

# Dates & Times
created_at: datetime auto_add    # Set on creation
updated_at: datetime auto_update # Update on save
birthdate: date optional         # Date only
start_time: time optional        # Time only

# Special Types
id: uuid pk                      # UUID primary key
email: email unique required     # Email validation
url: url optional                # URL validation
```

### Enums

```dsl
# Enum syntax: enum[Value1,Value2,Value3]
# Values can have spaces or underscores

status: enum[todo,in_progress,done]              # Basic enum
priority: enum[Low,Medium,High]                  # Capitalized
skill: enum[Beginner,Intermediate,Advanced]      # Multi-word

# With default (note the = syntax!)
status: enum[todo,in_progress,done]=todo         # ✓ CORRECT
priority: enum[Low,Medium,High]=Medium           # ✓ CORRECT

# WRONG syntaxes (will fail):
status: enum[todo,in_progress,done] default:"todo"  # ✗ WRONG
status: enum["todo","in_progress","done"]           # ✗ WRONG
status: enum(todo, in_progress, done)               # ✗ WRONG
```

---

## Default Values

**Golden Rule**: Use `=` for defaults, not `:` or `default=`

### Examples

```dsl
# Strings
name: str(100)="Untitled"              # ✓ String default
description: text="No description"     # ✓ Text default

# Numbers
count: int=0                           # ✓ Integer default
price: decimal(10,2)=0.00              # ✓ Decimal default

# Booleans
is_active: bool=true                   # ✓ Boolean (lowercase!)
is_verified: bool=false                # ✓ Boolean default

# Enums (use enum value, no quotes)
status: enum[todo,in_progress,done]=todo   # ✓ Enum default
priority: enum[Low,Medium,High]=Medium     # ✓ Capitalized enum

# Dates/Times
created_at: datetime auto_add           # Auto-set (no default needed)
updated_at: datetime auto_update        # Auto-update (no default needed)

# WRONG syntaxes:
name: str(100) default="Untitled"       # ✗ Use = not default=
is_active: bool default:true            # ✗ Use = not default:
status: enum[todo,done] default:"todo"  # ✗ Use = and no quotes
```

---

## Surface Modes

### Supported Modes (v0.1.0)

| Mode | Description | Use Case | Stack Support |
|------|-------------|----------|---------------|
| `list` | Table view | Browse records | All stacks |
| `view` | Detail view | View single record | All stacks |
| `create` | Creation form | Add new record | All stacks |
| `edit` | Edit form | Modify record | All stacks |

### Planned/Unsupported Modes

| Mode | Status | Workaround |
|------|--------|------------|
| `map` | ⏳ Planned v0.2 | Manual customization |
| `kanban` | ⏳ Planned v0.2 | Manual customization |
| `calendar` | ⏳ Planned v0.2 | Manual customization |
| `chart` | ⏳ Planned v0.3 | Manual customization |

### Surface Examples

```dsl
# List surface
surface task_list "All Tasks":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    field due_date "Due"

# Detail/View surface
surface task_detail "Task Details":
  uses entity Task
  mode: view

  section main "Task Information":
    field title "Title"
    field description "Description"
    field status "Status"

# Create surface
surface task_create "New Task":
  uses entity Task
  mode: create

  section main "Task Details":
    field title "Title"
    field description "Description"

# Edit surface
surface task_edit "Edit Task":
  uses entity Task
  mode: edit

  section main "Task Details":
    field title "Title"
    field description "Description"
    field status "Status"
```

---

## Relationships

### Foreign Keys

```dsl
# Foreign key syntax: ref EntityName
# Use 'ref' not 'fk'!

entity Task:
  id: uuid pk
  title: str(200) required
  owner: ref User required          # ✓ Foreign key to User
  project: ref Project optional     # ✓ Optional FK

entity User:
  id: uuid pk
  name: str(100) required

entity Project:
  id: uuid pk
  name: str(100) required

# WRONG syntaxes:
owner: fk User                      # ✗ Use 'ref' not 'fk'
owner: foreignkey User              # ✗ Use 'ref'
owner: User                         # ✗ Must use 'ref' keyword
```

### Many-to-Many

```dsl
# Not yet supported in v0.1.0
# Workaround: Create junction entity manually

entity TaskTag:
  id: uuid pk
  task: ref Task required
  tag: ref Tag required
```

---

## Common Patterns

### CRUD Entity (Minimal)

```dsl
entity Article:
  id: uuid pk
  title: str(200) required
  content: text required
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

### CRUD Entity (Full)

```dsl
entity Article:
  id: uuid pk
  title: str(200) required unique
  slug: str(200) required unique
  content: text required
  status: enum[draft,published,archived]=draft
  author: ref User required
  category: ref Category optional
  view_count: int=0
  is_featured: bool=false
  published_at: datetime optional
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

### Complete CRUD Surfaces

```dsl
# List
surface article_list "Articles":
  uses entity Article
  mode: list

  section main "All Articles":
    field title "Title"
    field status "Status"
    field author "Author"
    field created_at "Created"

# Detail
surface article_detail "Article":
  uses entity Article
  mode: view

  section main "Article":
    field title "Title"
    field content "Content"
    field status "Status"
    field author "Author"

# Create
surface article_create "New Article":
  uses entity Article
  mode: create

  section main "Article Details":
    field title "Title"
    field content "Content"
    field author "Author"
    field category "Category"

# Edit
surface article_edit "Edit Article":
  uses entity Article
  mode: edit

  section main "Article Details":
    field title "Title"
    field content "Content"
    field status "Status"
    field category "Category"
```

### Audit Fields Pattern

```dsl
# Add to any entity for audit trail
entity MyEntity:
  id: uuid pk
  # ... your fields ...
  created_at: datetime auto_add
  created_by: ref User required
  updated_at: datetime auto_update
  updated_by: ref User required
```

### Soft Delete Pattern

```dsl
entity MyEntity:
  id: uuid pk
  # ... your fields ...
  is_deleted: bool=false
  deleted_at: datetime optional
  deleted_by: ref User optional
```

### Access Control Pattern (v0.5.0+)

```dsl
# Inline access rules for read/write permissions
entity Task:
  id: uuid pk
  title: str(200) required
  owner_id: ref User required
  is_public: bool=false

  access:
    read: owner_id = current_user or is_public = true
    write: owner_id = current_user

# read: maps to visibility rules (who can see records)
# write: maps to create/update/delete permissions
```

---

## Reserved Keywords

### ⚠️ Don't Use These as Project/Module Names

```
app, module, entity, surface, experience, service,
foreign_model, integration, test, use, section,
field, action, true, false, null, none,
access, read, write, visible, permissions
```

### Project Name Validation

```bash
# ✓ GOOD project names
dazzle init my_project
dazzle init awesome-tool
dazzle init UrbanCanopy

# ✗ BAD project names (will fail)
dazzle init test          # Reserved keyword
dazzle init app           # Reserved keyword
dazzle init 123project    # Can't start with number
```

---

## Gotchas & Solutions

### 1. Default Value Syntax

**Problem**: `default="value"` doesn't work

**Solution**: Use `=value` directly
```dsl
# ✗ WRONG
name: str(100) default="Untitled"

# ✓ CORRECT
name: str(100)="Untitled"
```

### 2. Enum Default with Quotes

**Problem**: `status: enum[todo,done] default:"todo"` fails

**Solution**: No quotes, use `=`
```dsl
# ✗ WRONG
status: enum[todo,done] default:"todo"

# ✓ CORRECT
status: enum[todo,done]=todo
```

### 3. Foreign Key Syntax

**Problem**: `owner: fk User` doesn't work

**Solution**: Use `ref` keyword
```dsl
# ✗ WRONG
owner: fk User
owner: foreignkey User
owner: User

# ✓ CORRECT
owner: ref User required
```

### 4. Boolean Defaults

**Problem**: `is_active: bool default=True` fails

**Solution**: Use lowercase `true/false`
```dsl
# ✗ WRONG
is_active: bool default=True
is_active: bool default:true

# ✓ CORRECT
is_active: bool=true
```

### 5. Auto-timestamp Syntax

**Problem**: `created_at: datetime auto_now` doesn't work

**Solution**: Use `auto_add` and `auto_update`
```dsl
# ✗ WRONG
created_at: datetime auto_now
updated_at: datetime auto_now_add

# ✓ CORRECT
created_at: datetime auto_add      # Set on creation
updated_at: datetime auto_update   # Update on save
```

### 6. Project Name "test"

**Problem**: Cryptic error with project named "test"

**Solution**: Use different name (test is reserved)
```bash
# ✗ WRONG
dazzle init test

# ✓ CORRECT
dazzle init my_test_app
dazzle init testing_tool
```

### 7. Help Text on Fields

**Problem**: `field title "Title" help="Enter title"` not supported

**Solution**: Not yet supported in v0.1.0
```dsl
# ⏳ Planned for v0.2
# For now: Use Django admin customization
```

### 8. Map/Kanban Surface Modes

**Problem**: `mode: map` or `mode: kanban` fails validation

**Solution**: Not yet supported
```dsl
# ⏳ Planned for v0.2
# For now: Use manual Django template customization
```

---

## Quick Syntax Cheat Sheet

```dsl
# Module & App
module myapp.core
app myapp "My Application"

# Basic Entity
entity Task:
  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[todo,done]=todo
  owner: ref User required
  is_active: bool=true
  created_at: datetime auto_add
  updated_at: datetime auto_update

# Basic Surface
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main "All Tasks":
    field title "Title"
    field status "Status"
    field owner "Owner"

# Field Type Reference
str(N)              # String with max length
text                # Long text (no limit)
int                 # Integer
decimal(P,S)        # Decimal (precision, scale)
float               # Floating point
bool                # Boolean
date                # Date only
time                # Time only
datetime            # Date and time
uuid                # UUID
email               # Email (validated)
url                 # URL (validated)
enum[A,B,C]         # Enum with values
ref EntityName      # Foreign key

# Constraints
required            # Not null
optional            # Nullable (default)
unique              # Unique constraint
pk                  # Primary key

# Auto-timestamps
auto_add            # Set on creation
auto_update         # Update on save

# Default values
=value              # Set default (use = not :)
```

---

## Examples by Use Case

### Blog Application

```dsl
module blog.core

app blog "Simple Blog"

entity User:
  id: uuid pk
  username: str(100) required unique
  email: email required unique
  is_staff: bool=false
  created_at: datetime auto_add

entity Post:
  id: uuid pk
  title: str(200) required
  slug: str(200) required unique
  content: text required
  author: ref User required
  status: enum[draft,published]=draft
  created_at: datetime auto_add
  updated_at: datetime auto_update

surface post_list "Posts":
  uses entity Post
  mode: list

  section main "All Posts":
    field title "Title"
    field author "Author"
    field status "Status"
```

### Inventory System

```dsl
module inventory.core

app inventory "Inventory Manager"

entity Product:
  id: uuid pk
  sku: str(50) required unique
  name: str(200) required
  quantity: int=0
  price: decimal(10,2) required
  category: ref Category required
  is_active: bool=true

entity Category:
  id: uuid pk
  name: str(100) required unique

surface product_list "Products":
  uses entity Product
  mode: list

  section main "Products":
    field sku "SKU"
    field name "Name"
    field quantity "Stock"
    field price "Price"
```

### Project Management

```dsl
module pm.core

app pm "Project Manager"

entity Project:
  id: uuid pk
  name: str(200) required
  status: enum[planning,active,completed]=planning
  start_date: date required
  end_date: date optional

entity Task:
  id: uuid pk
  project: ref Project required
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  priority: enum[Low,Medium,High]=Medium
  due_date: date optional
  assigned_to: ref User optional

entity User:
  id: uuid pk
  name: str(100) required
  email: email required unique
```

---

## Error Message Translation Guide

| Error Message | Meaning | Solution |
|---------------|---------|----------|
| `Expected :, got =` | Wrong syntax for field definition | Check field syntax |
| `Expected IDENTIFIER, got test` | Reserved keyword used | Rename project/module |
| `Unknown field type: fk` | Wrong FK syntax | Use `ref EntityName` |
| `Invalid default value syntax` | Wrong default syntax | Use `=value` not `default=value` |
| `Mode 'map' not supported` | Unsupported surface mode | Use list/view/create/edit |

---

## When You're Stuck

1. **Read this guide** - Most issues are syntax-related
2. **Check examples** - `/Volumes/SSD/Dazzle/examples/`
3. **Run validate** - `dazzle validate` gives specific errors
4. **Start simple** - Get basic CRUD working first
5. **Ask Claude** - Paste error message + this guide

---

## What's NOT in v0.1.0 (Yet)

- Map surfaces (use manual templates)
- Kanban boards (use manual templates)
- File uploads (field exists, UI manual)
- Many-to-many relationships (use junction entity)
- Custom validators (use Django customization)
- Complex experiences (multi-step workflows - basic only)
- Help text on fields (use Django admin)

**These are planned for v0.2+**

---

**Last Updated**: 2025-11-23
**DAZZLE Version**: 0.1.0
**Found an error?** Open an issue with the example that didn't work!
