# BackendSpec Reference

Complete reference for DNR backend specification types.

## Overview

BackendSpec defines your application's backend structure:
- Entities (data models)
- Services (business logic)
- Endpoints (HTTP API)
- Auth rules (security)

## BackendSpec

Root specification for the backend.

```python
class BackendSpec:
    name: str                           # Application name
    version: str = "1.0.0"             # API version
    entities: list[EntitySpec]          # Data models
    services: list[ServiceSpec]         # Business operations
    endpoints: list[EndpointSpec]       # HTTP routes
    auth_rules: list[AuthRuleSpec]      # Authentication rules
```

## EntitySpec

Defines a data model (maps to database table/collection).

```python
class EntitySpec:
    name: str                           # Entity name (PascalCase)
    label: str | None                   # Human-readable label
    fields: list[FieldSpec]             # Entity fields
    relations: list[RelationSpec]       # Relationships
    validators: list[ValidatorSpec]     # Entity-level validation
```

### Example

```python
EntitySpec(
    name="Task",
    label="Task",
    fields=[
        FieldSpec(name="id", type=ScalarType.UUID, required=True, primary_key=True),
        FieldSpec(name="title", type=ScalarType.STRING, max_length=200, required=True),
        FieldSpec(name="status", type=ScalarType.STRING, default="pending"),
        FieldSpec(name="created_at", type=ScalarType.DATETIME, auto_now_add=True),
    ]
)
```

## FieldSpec

Defines a field within an entity.

```python
class FieldSpec:
    name: str                           # Field name (snake_case)
    type: ScalarType | EnumType | RefType  # Field type
    required: bool = False              # Is field required?
    default: Any | None                 # Default value
    max_length: int | None              # For string fields
    primary_key: bool = False           # Is primary key?
    unique: bool = False                # Unique constraint?
    indexed: bool = False               # Create index?
    auto_now_add: bool = False          # Set on create?
    auto_now: bool = False              # Set on update?
    validators: list[ValidatorSpec]     # Field validators
```

### Scalar Types

| Type | Python Type | Description |
|------|-------------|-------------|
| `STRING` | `str` | Text field |
| `TEXT` | `str` | Long text |
| `INTEGER` | `int` | Whole number |
| `DECIMAL` | `Decimal` | Precise decimal |
| `BOOLEAN` | `bool` | True/false |
| `DATE` | `date` | Date only |
| `DATETIME` | `datetime` | Date and time |
| `UUID` | `UUID` | Unique identifier |
| `EMAIL` | `str` | Email address |

### EnumType

Constrained set of values:

```python
EnumType(
    name="TaskStatus",
    values=["pending", "in_progress", "completed"]
)
```

### RefType

Reference to another entity:

```python
RefType(entity="User")
```

## RelationSpec

Defines relationships between entities.

```python
class RelationSpec:
    name: str                           # Relation name
    target: str                         # Target entity name
    kind: RelationKind                  # Relationship type
    backref: str | None                 # Reverse relation name
    required: bool = False              # Is required?
    on_delete: str = "restrict"         # Cascade behavior
```

### RelationKind

| Kind | Description |
|------|-------------|
| `ONE_TO_ONE` | Single related entity |
| `ONE_TO_MANY` | Multiple related entities |
| `MANY_TO_ONE` | Foreign key reference |
| `MANY_TO_MANY` | Many-to-many relationship |

### Example

```python
RelationSpec(
    name="assignee",
    target="User",
    kind=RelationKind.MANY_TO_ONE,
    backref="assigned_tasks",
    required=False,
    on_delete="nullify"
)
```

## ValidatorSpec

Validation rules for fields or entities.

```python
class ValidatorSpec:
    kind: ValidatorKind                 # Validator type
    value: Any | None                   # Validator parameter
    message: str | None                 # Error message
```

### ValidatorKind

| Kind | Parameter | Description |
|------|-----------|-------------|
| `REQUIRED` | - | Field must have value |
| `MIN_LENGTH` | `int` | Minimum string length |
| `MAX_LENGTH` | `int` | Maximum string length |
| `MIN_VALUE` | `number` | Minimum numeric value |
| `MAX_VALUE` | `number` | Maximum numeric value |
| `PATTERN` | `str` | Regex pattern |
| `EMAIL` | - | Valid email format |
| `URL` | - | Valid URL format |
| `CUSTOM` | `str` | Custom validator name |

## ServiceSpec

Defines business operations.

```python
class ServiceSpec:
    name: str                           # Service name
    entity: str                         # Target entity
    operations: list[DomainOperation]   # Available operations
    schemas: list[SchemaSpec]           # Input/output schemas
    rules: list[BusinessRuleSpec]       # Business rules
```

### DomainOperation

```python
class DomainOperation:
    name: str                           # Operation name
    kind: OperationKind                 # Operation type
    input_schema: str | None            # Input schema name
    output_schema: str | None           # Output schema name
    effects: list[EffectSpec]           # Side effects
```

### OperationKind

| Kind | Description |
|------|-------------|
| `CREATE` | Create new entity |
| `READ` | Read single entity |
| `UPDATE` | Update existing entity |
| `DELETE` | Delete entity |
| `LIST` | List entities with filtering |
| `CUSTOM` | Custom operation |

## EndpointSpec

Maps services to HTTP routes.

```python
class EndpointSpec:
    name: str                           # Endpoint name
    path: str                           # URL path
    method: HttpMethod                  # HTTP method
    service: str                        # Service name
    operation: str                      # Operation name
    auth: list[AuthRuleSpec]            # Auth requirements
    rate_limit: RateLimitSpec | None    # Rate limiting
```

### HttpMethod

| Method | Use Case |
|--------|----------|
| `GET` | Read operations |
| `POST` | Create operations |
| `PUT` | Full update |
| `PATCH` | Partial update |
| `DELETE` | Delete operations |

### Path Parameters

Use curly braces for dynamic segments:

```python
EndpointSpec(
    path="/tasks/{task_id}",
    method=HttpMethod.GET,
    service="TaskService",
    operation="read"
)
```

## AuthRuleSpec

Authentication and authorization rules.

```python
class AuthRuleSpec:
    kind: str                           # "jwt", "api_key", "session"
    required: bool = True               # Is auth required?
    roles: list[str]                    # Required roles
    permissions: list[str]              # Required permissions
```

### Example

```python
AuthRuleSpec(
    kind="jwt",
    required=True,
    roles=["admin", "manager"],
    permissions=["task.write"]
)
```

## RateLimitSpec

Rate limiting configuration.

```python
class RateLimitSpec:
    requests: int                       # Max requests
    period: int                         # Time period (seconds)
    scope: str = "ip"                   # "ip", "user", "global"
```

## Complete Example

```python
BackendSpec(
    name="task_manager",
    version="1.0.0",
    entities=[
        EntitySpec(
            name="Task",
            fields=[
                FieldSpec(name="id", type=ScalarType.UUID, primary_key=True),
                FieldSpec(name="title", type=ScalarType.STRING, max_length=200, required=True),
                FieldSpec(name="status", type=EnumType("TaskStatus", ["pending", "done"])),
            ]
        )
    ],
    services=[
        ServiceSpec(
            name="TaskService",
            entity="Task",
            operations=[
                DomainOperation(name="list", kind=OperationKind.LIST),
                DomainOperation(name="create", kind=OperationKind.CREATE),
                DomainOperation(name="read", kind=OperationKind.READ),
                DomainOperation(name="update", kind=OperationKind.UPDATE),
                DomainOperation(name="delete", kind=OperationKind.DELETE),
            ]
        )
    ],
    endpoints=[
        EndpointSpec(path="/tasks", method=HttpMethod.GET, service="TaskService", operation="list"),
        EndpointSpec(path="/tasks", method=HttpMethod.POST, service="TaskService", operation="create"),
        EndpointSpec(path="/tasks/{id}", method=HttpMethod.GET, service="TaskService", operation="read"),
        EndpointSpec(path="/tasks/{id}", method=HttpMethod.PUT, service="TaskService", operation="update"),
        EndpointSpec(path="/tasks/{id}", method=HttpMethod.DELETE, service="TaskService", operation="delete"),
    ]
)
```

## JSON Serialization

BackendSpec can be serialized to JSON:

```python
spec.model_dump_json(indent=2)
```

And restored:

```python
BackendSpec.model_validate_json(json_string)
```
