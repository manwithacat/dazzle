# Modules and App Declaration

Every DAZZLE file must declare its module and optionally define app metadata.

## Module Declaration

```dsl
module module_name
```

The module name must be a valid identifier (letters, numbers, underscores). All constructs in the file belong to this module.

### Multi-Module Projects

Large projects can span multiple modules. Use `use` declarations to reference constructs from other modules:

```dsl
module billing

use inventory.core      # Import all from inventory.core module
use crm.customers       # Import all from crm.customers module

entity Invoice "Invoice":
  id: uuid pk
  customer: ref Customer   # From crm.customers
  items: has_many LineItem
```

**Use Declaration Syntax:**
```dsl
use other_module.name     # Import from another module
use parent.child.name     # Import from nested module path
```

## App Declaration

Define application metadata (typically in the main module):

```dsl
app app_name "Display Title"
```

### Example

```dsl
module my_company.inventory
app inventory_tracker "Inventory Tracker"

# Constructs follow...
```

## File Organization

Recommended structure for multi-module projects:

```
dsl/
  core.dsl           # module my_app.core - shared entities
  customers.dsl      # module my_app.customers - customer management
  billing.dsl        # module my_app.billing - billing (uses core, customers)
  app.dsl            # module my_app - app declaration, workspaces
```

## Cross-Module References

When referencing entities from other modules:

1. Add `use` declaration at top of file
2. Reference by simple name (not qualified)

```dsl
module my_app.orders

use my_app.core         # Contains Product entity
use my_app.customers    # Contains Customer entity

entity Order "Order":
  id: uuid pk
  customer: ref Customer    # Resolved via use declaration
  items: has_many OrderItem

entity OrderItem "Order Item":
  id: uuid pk
  order: belongs_to Order
  product: ref Product      # From core module
  quantity: int required
```
