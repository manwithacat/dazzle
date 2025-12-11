# Entities

Entities are the core data models in DAZZLE. They define structure, relationships, and constraints.

## Basic Syntax

```dsl
entity EntityName "Display Title":
  field_name: type modifiers
```

## Field Types

### Primitive Types

| Type | Description | Example |
|------|-------------|---------|
| `str(N)` | String with max length N | `name: str(100)` |
| `text` | Unlimited text | `description: text` |
| `int` | Integer | `quantity: int` |
| `decimal(P,S)` | Decimal with precision P, scale S | `price: decimal(10,2)` |
| `bool` | Boolean | `active: bool` |
| `date` | Date only | `birth_date: date` |
| `datetime` | Date and time | `created_at: datetime` |
| `uuid` | UUID identifier | `id: uuid` |
| `email` | Email address (validated) | `contact: email` |

### Enum Type

Define inline enumeration values:

```dsl
status: enum[draft,pending,approved,rejected]
priority: enum[low,medium,high,critical]
```

Enum values can include reserved keywords:

```dsl
status: enum[draft,submitted,approved] = draft
```

### Reference Types

| Type | Description | Example |
|------|-------------|---------|
| `ref Entity` | Foreign key reference | `author: ref User` |
| `has_many Entity` | One-to-many relationship | `items: has_many OrderItem` |
| `has_one Entity` | One-to-one relationship | `profile: has_one UserProfile` |
| `belongs_to Entity` | Inverse of has_many/has_one | `order: belongs_to Order` |
| `embeds Entity` | Embedded/nested entity | `address: embeds Address` |

## Field Modifiers

| Modifier | Description |
|----------|-------------|
| `required` | Field cannot be null |
| `optional` | Field can be null (default) |
| `pk` | Primary key |
| `unique` | Unique constraint |
| `unique?` | Unique but nullable |
| `auto_add` | Auto-set on creation (datetime) |
| `auto_update` | Auto-set on update (datetime) |
| `= value` | Default value |

## Relationship Modifiers

For `has_many` and `has_one`:

| Modifier | Description |
|----------|-------------|
| `cascade` | Delete children when parent deleted |
| `restrict` | Prevent deletion if children exist |
| `nullify` | Set foreign key to null on delete |
| `readonly` | Relationship is read-only |

```dsl
items: has_many OrderItem cascade
profile: has_one UserProfile restrict
comments: has_many Comment nullify readonly
```

## Complete Example

```dsl
entity Order "Customer Order":
  # Primary key
  id: uuid pk

  # Simple fields
  order_number: str(20) required unique
  notes: text optional

  # Numeric
  subtotal: decimal(10,2) required
  tax_rate: decimal(5,4) = 0.0825
  item_count: int = 0

  # Enum with default
  status: enum[draft,submitted,processing,shipped,delivered,cancelled] = draft
  priority: enum[low,normal,high] = normal

  # Dates
  order_date: date required
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Boolean
  is_gift: bool = false
  requires_signature: bool = false

  # References
  customer: ref Customer required
  shipping_address: embeds Address
  billing_address: embeds Address

  # Relationships
  items: has_many OrderItem cascade
  shipments: has_many Shipment restrict
  notes: has_many OrderNote nullify

entity OrderItem "Order Line Item":
  id: uuid pk
  order: belongs_to Order
  product: ref Product required
  quantity: int required
  unit_price: decimal(10,2) required
  line_total: decimal(10,2) required

entity Address "Address":
  street: str(200) required
  city: str(100) required
  state: str(50)
  postal_code: str(20) required
  country: str(2) required = "US"
```

## Embedded Entities

Use `embeds` for nested data that doesn't need its own table:

```dsl
entity Contact "Contact":
  id: uuid pk
  name: str(100) required
  work_address: embeds Address
  home_address: embeds Address

entity Address "Address":
  street: str(200)
  city: str(100)
  postal_code: str(20)
```

Embedded entities are stored inline (as JSON or flattened columns depending on backend).

## Self-Referential Relationships

Entities can reference themselves:

```dsl
entity Category "Category":
  id: uuid pk
  name: str(100) required
  parent: ref Category optional
  children: has_many Category cascade

entity Employee "Employee":
  id: uuid pk
  name: str(100) required
  manager: ref Employee optional
  direct_reports: has_many Employee nullify
```

## Best Practices

1. **Always define a primary key** - Use `id: uuid pk` by convention
2. **Use timestamps** - Add `created_at` and `updated_at` with auto modifiers
3. **Choose relationship behavior** - Specify cascade/restrict/nullify explicitly
4. **Use enums for fixed sets** - Better than strings for status fields
5. **Keep embedded entities simple** - Complex nested data should be separate entities
