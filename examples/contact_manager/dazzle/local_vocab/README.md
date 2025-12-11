# Contact Manager - Vocabulary Reference

Domain-specific patterns for contact/CRM management applications.

## Available Entries

### Common Data Patterns

#### `audit_fields` (macro)
Standard audit timestamp fields.
```dsl
@use audit_fields()
# Expands to:
# created_at: datetime auto_add
# updated_at: datetime auto_update
```

### CRM-Specific Patterns

#### `contact_name_fields` (macro)
First and last name fields for person contacts.
```dsl
@use contact_name_fields()
# Expands to:
# first_name: str(100) required
# last_name: str(100) required

@use contact_name_fields(first_max_length=50, last_max_length=50)
# Custom field lengths
```

#### `contact_info_fields` (macro)
Email and phone contact information.
```dsl
@use contact_info_fields()
# Expands to:
# email: email unique required
# phone: str(20)

@use contact_info_fields(email_required=false, email_unique=false)
# Optional, non-unique email
```

#### `company_fields` (macro)
Company and job title fields for business contacts.
```dsl
@use company_fields()
# Expands to:
# company: str(200)
# job_title: str(150)
```

#### `favorite_field` (alias)
Boolean field to mark favorites/starred items.
```dsl
@use favorite_field()
# Expands to: is_favorite: bool=false

@use favorite_field(field_name=starred)
# Expands to: starred: bool=false
```

### Entity Templates

#### `contact_entity` (pattern)
Complete contact entity template.
```dsl
@use contact_entity()
# Generates complete Contact entity with all standard fields
```

### UI Patterns

#### `crud_surface_set` (pattern)
Complete CRUD surface set.
```dsl
@use crud_surface_set(entity_name=Contact, title_field=first_name)
# Generates: contact_list, contact_detail, contact_create, contact_edit
```

## Usage Example

```dsl
module crm.core
app crm "Contact Manager"

# Option 1: Use full entity template
@use contact_entity()

# Option 2: Build custom entity with patterns
entity Contact "Contact":
  id: uuid pk
  @use contact_name_fields()
  @use contact_info_fields()
  @use company_fields()
  notes: text
  @use favorite_field()
  @use audit_fields()

# Generate all CRUD surfaces
@use crud_surface_set(entity_name=Contact, title_field=first_name)
```

## Commands

```bash
dazzle vocab list              # List all entries
dazzle vocab show contact_entity  # Show entry details
dazzle vocab list --tag crm    # Filter by tag
```

## Tags

- `crm`, `contact` - CRM-specific patterns
- `common` - Frequently used patterns
- `audit`, `timestamp` - Time tracking
- `crud`, `ui` - User interface patterns
