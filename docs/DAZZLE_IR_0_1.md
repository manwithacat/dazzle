# DAZZLE Internal Representation (IR) 0.1

**Version**: 0.1.0
**Last Updated**: 2025-11-23
**Implementation**: `src/dazzle/core/ir.py`

This document describes the complete Internal Representation (IR) used by DAZZLE. The IR is the framework-agnostic, typed representation of an application built from DSL specifications.

---

## Table of Contents

1. [Overview](#overview)
2. [IR Flow](#ir-flow)
3. [Design Principles](#design-principles)
4. [Type Reference](#type-reference)
5. [Examples](#examples)

---

## Overview

### What is the IR?

The DAZZLE IR is a **complete, typed, immutable representation** of an application specification. It serves as:

- **Single source of truth** for all code generation
- **Framework-agnostic model** - Not tied to Django, Express, or any specific technology
- **Validation target** - All semantic checks operate on the IR
- **Communication format** - Shared between parser, linker, validators, and generators

### Implementation

The IR is implemented as **Pydantic models** in `src/dazzle/core/ir.py` (900+ lines):

```python
from pydantic import BaseModel, Field

class EntitySpec(BaseModel):
    name: str
    fields: List[FieldSpec]
    # ...

    class Config:
        frozen = True  # Immutable!
```

**Key characteristics**:
- ✅ **Type-safe** - Pydantic validates all data
- ✅ **Immutable** - All models use `frozen=True`
- ✅ **Serializable** - Can convert to/from JSON
- ✅ **Self-documenting** - Rich property methods and docstrings

---

## IR Flow

### From DSL to Generated Code

```
┌──────────┐
│   .dsl   │  DSL files
│  files   │
└────┬─────┘
     │
     ▼
┌──────────────┐
│ Parser       │  dsl_parser.py parses each file
│              │
└────┬─────────┘
     │
     ▼
┌──────────────┐
│ ModuleIR     │  One per .dsl file
│ + Fragment   │  Contains entities, surfaces, etc.
└────┬─────────┘
     │
     ▼
┌──────────────┐
│ Linker       │  linker.py merges modules
│              │  - Resolves dependencies
│              │  - Validates references
│              │  - Merges fragments
└────┬─────────┘
     │
     ▼
┌──────────────┐
│  AppSpec     │  Complete, validated app specification
│  (IR)        │  ← THIS IS THE IR
└────┬─────────┘
     │
     ├──────────────────┬──────────────────┬──────────────────┐
     ▼                  ▼                  ▼                  ▼
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Django   │     │ Express  │     │ OpenAPI  │     │  Docker  │
│ Stack    │     │  Stack   │     │  Stack   │     │  Stack   │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
     │                  │                  │                  │
     ▼                  ▼                  ▼                  ▼
  Django app      Express app       openapi.yaml     docker-compose.yml
```

### Pipeline Details

**1. Parsing** (`dsl_parser.py`):
- Reads `.dsl` files
- Creates `ModuleIR` for each file
- Extracts `ModuleFragment` (entities, surfaces, etc.)
- Returns `List[ModuleIR]`

**2. Linking** (`linker.py`):
- Topological sort (dependency order)
- Builds symbol table
- Validates cross-references
- Merges fragments → `AppSpec`

**3. Validation** (`lint.py`):
- Type checking
- Reference validation
- Constraint validation
- Pattern detection

**4. Generation** (stacks):
- Each stack consumes `AppSpec`
- Generates framework-specific code
- No re-parsing needed

---

## Design Principles

### 1. Immutability

**All IR types use `frozen=True`**:

```python
class EntitySpec(BaseModel):
    name: str
    fields: List[FieldSpec]

    class Config:
        frozen = True  # Cannot modify after creation
```

**Benefits**:
- ✅ **Thread-safe** - Can parallelize stack generation
- ✅ **Cacheable** - Hash-based deduplication
- ✅ **Predictable** - State never changes unexpectedly
- ✅ **Debuggable** - No hidden mutations

**Implications**:
```python
# ❌ This will raise an error:
entity.name = "NewName"  # FrozenInstanceError

# ✅ Create new instance instead:
new_entity = entity.model_copy(update={"name": "NewName"})
```

### 2. Type Safety

Pydantic validates all data:

```python
field = FieldSpec(
    name="email",
    type=FieldType(kind=FieldTypeKind.EMAIL),
    modifiers=[FieldModifier.REQUIRED]
)

# Pydantic ensures:
# - name is a string
# - type is a valid FieldType
# - modifiers are valid FieldModifiers
```

### 3. Framework Agnosticism

The IR contains **no framework-specific details**:

```python
# ✅ Good (framework-agnostic)
FieldType(kind=FieldTypeKind.STR, max_length=200)

# ❌ Bad (Django-specific)
FieldType(kind="CharField", max_length=200)
```

Stacks handle framework mapping:
- Django: `str(200)` → `models.CharField(max_length=200)`
- Express: `str(200)` → `DataTypes.STRING(200)`
- OpenAPI: `str(200)` → `type: string, maxLength: 200`

### 4. Rich Property Methods

IR types provide convenience methods:

```python
entity = EntitySpec(...)

# Instead of looping through fields:
pk = entity.primary_key          # → Optional[FieldSpec]
field = entity.get_field("email") # → Optional[FieldSpec]

# Check field properties:
if field.is_required:
    ...
if field.is_unique:
    ...
```

---

## Type Reference

### Core Types

#### FieldTypeKind

```python
class FieldTypeKind(str, Enum):
    STR = "str"        # Variable-length string
    TEXT = "text"      # Unlimited text
    INT = "int"        # 32-bit integer
    DECIMAL = "decimal" # Fixed-point decimal
    BOOL = "bool"      # Boolean
    DATE = "date"      # Date only
    DATETIME = "datetime" # Date and time
    UUID = "uuid"      # UUID v4
    ENUM = "enum"      # Enumerated values
    REF = "ref"        # Foreign key reference
    EMAIL = "email"    # Email with validation
```

**Usage in DSL**:
```dsl
entity User:
  id: uuid pk                    # FieldTypeKind.UUID
  email: email required          # FieldTypeKind.EMAIL
  name: str(200) required        # FieldTypeKind.STR
  bio: text                      # FieldTypeKind.TEXT
  age: int                       # FieldTypeKind.INT
  balance: decimal(10,2)         # FieldTypeKind.DECIMAL
  is_active: bool=true           # FieldTypeKind.BOOL
  birth_date: date               # FieldTypeKind.DATE
  created_at: datetime auto_add  # FieldTypeKind.DATETIME
  role: enum[admin,user]         # FieldTypeKind.ENUM
  company: ref Company           # FieldTypeKind.REF
```

#### FieldType

```python
class FieldType(BaseModel):
    kind: FieldTypeKind
    max_length: Optional[int] = None     # for str
    precision: Optional[int] = None      # for decimal
    scale: Optional[int] = None          # for decimal
    enum_values: Optional[List[str]] = None  # for enum
    ref_entity: Optional[str] = None     # for ref

    class Config:
        frozen = True
```

**Examples**:

```python
# str(200)
FieldType(kind=FieldTypeKind.STR, max_length=200)

# decimal(10,2)
FieldType(kind=FieldTypeKind.DECIMAL, precision=10, scale=2)

# enum[draft,issued,paid]
FieldType(
    kind=FieldTypeKind.ENUM,
    enum_values=["draft", "issued", "paid"]
)

# ref Client
FieldType(kind=FieldTypeKind.REF, ref_entity="Client")
```

**JSON Example**:
```json
{
  "kind": "str",
  "max_length": 200,
  "precision": null,
  "scale": null,
  "enum_values": null,
  "ref_entity": null
}
```

#### FieldModifier

```python
class FieldModifier(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    PK = "pk"                    # Primary key
    UNIQUE = "unique"            # Unique constraint
    UNIQUE_NULLABLE = "unique?"  # Unique but nullable
    AUTO_ADD = "auto_add"        # Auto-set on create
    AUTO_UPDATE = "auto_update"  # Auto-update on save
```

#### FieldSpec

```python
class FieldSpec(BaseModel):
    name: str
    type: FieldType
    modifiers: List[FieldModifier] = Field(default_factory=list)
    default: Optional[Union[str, int, float, bool]] = None

    class Config:
        frozen = True

    @property
    def is_required(self) -> bool: ...

    @property
    def is_primary_key(self) -> bool: ...

    @property
    def is_unique(self) -> bool: ...
```

**Example**:
```python
FieldSpec(
    name="email",
    type=FieldType(kind=FieldTypeKind.EMAIL),
    modifiers=[FieldModifier.REQUIRED, FieldModifier.UNIQUE],
    default=None
)
```

**JSON Example**:
```json
{
  "name": "email",
  "type": {
    "kind": "email",
    "max_length": null,
    "precision": null,
    "scale": null,
    "enum_values": null,
    "ref_entity": null
  },
  "modifiers": ["required", "unique"],
  "default": null
}
```

---

### Domain Types

#### Constraint

```python
class ConstraintKind(str, Enum):
    UNIQUE = "unique"  # Multi-field unique
    INDEX = "index"    # Performance index

class Constraint(BaseModel):
    kind: ConstraintKind
    fields: List[str]  # Field names

    class Config:
        frozen = True
```

**DSL Example**:
```dsl
entity Invoice:
  client: ref Client
  number: str(20)

  unique: client, number  # One invoice number per client
  index: created_at desc
```

**IR Example**:
```python
[
    Constraint(kind=ConstraintKind.UNIQUE, fields=["client", "number"]),
    Constraint(kind=ConstraintKind.INDEX, fields=["created_at"])
]
```

#### EntitySpec

```python
class EntitySpec(BaseModel):
    name: str
    title: Optional[str] = None
    fields: List[FieldSpec]
    constraints: List[Constraint] = Field(default_factory=list)

    class Config:
        frozen = True

    @property
    def primary_key(self) -> Optional[FieldSpec]:
        """Get the primary key field."""
        ...

    def get_field(self, name: str) -> Optional[FieldSpec]:
        """Get field by name."""
        ...
```

**Complete Example**:
```python
EntitySpec(
    name="User",
    title="User Account",
    fields=[
        FieldSpec(
            name="id",
            type=FieldType(kind=FieldTypeKind.UUID),
            modifiers=[FieldModifier.PK]
        ),
        FieldSpec(
            name="email",
            type=FieldType(kind=FieldTypeKind.EMAIL),
            modifiers=[FieldModifier.REQUIRED, FieldModifier.UNIQUE]
        ),
        FieldSpec(
            name="username",
            type=FieldType(kind=FieldTypeKind.STR, max_length=50),
            modifiers=[FieldModifier.REQUIRED, FieldModifier.UNIQUE]
        ),
    ],
    constraints=[
        Constraint(kind=ConstraintKind.UNIQUE, fields=["email", "username"])
    ]
)
```

#### DomainSpec

```python
class DomainSpec(BaseModel):
    entities: List[EntitySpec] = Field(default_factory=list)

    class Config:
        frozen = True

    def get_entity(self, name: str) -> Optional[EntitySpec]:
        """Get entity by name."""
        ...
```

---

### Surface Types

#### SurfaceMode

```python
class SurfaceMode(str, Enum):
    VIEW = "view"      # Read-only detail
    CREATE = "create"  # Create new entity
    EDIT = "edit"      # Update existing
    LIST = "list"      # List multiple entities
    CUSTOM = "custom"  # Custom behavior
```

#### SurfaceElement

```python
class SurfaceElement(BaseModel):
    name: str
    label: Optional[str] = None
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    read_only: bool = False

    class Config:
        frozen = True
```

#### SurfaceSection

```python
class SurfaceSection(BaseModel):
    name: str
    title: Optional[str] = None
    elements: List[SurfaceElement] = Field(default_factory=list)

    class Config:
        frozen = True
```

#### OutcomeKind

```python
class OutcomeKind(str, Enum):
    SURFACE = "surface"          # Navigate to surface
    EXPERIENCE = "experience"    # Start experience
    INTEGRATION = "integration"  # Call integration
```

#### ActionOutcome

```python
class ActionOutcome(BaseModel):
    kind: OutcomeKind
    target: str  # Surface/experience/integration name

    class Config:
        frozen = True
```

#### SurfaceAction

```python
class SurfaceAction(BaseModel):
    name: str
    label: Optional[str] = None
    outcome: ActionOutcome

    class Config:
        frozen = True
```

#### SurfaceSpec

```python
class SurfaceSpec(BaseModel):
    name: str
    title: Optional[str] = None
    entity_ref: Optional[str] = None
    mode: SurfaceMode
    sections: List[SurfaceSection] = Field(default_factory=list)
    actions: List[SurfaceAction] = Field(default_factory=list)

    class Config:
        frozen = True

    def get_section(self, name: str) -> Optional[SurfaceSection]:
        ...
```

---

### Experience Types

#### StepKind

```python
class StepKind(str, Enum):
    SURFACE = "surface"          # Show a surface
    INTEGRATION = "integration"  # Call integration
    PROCESS = "process"          # Backend process
```

#### StepTransition

```python
class StepTransition(BaseModel):
    on: str  # "success", "failure", "cancel", etc.
    next_step: str

    class Config:
        frozen = True
```

#### ExperienceStep

```python
class ExperienceStep(BaseModel):
    name: str
    kind: StepKind
    surface: Optional[str] = None       # if kind=surface
    integration: Optional[str] = None   # if kind=integration
    process: Optional[str] = None       # if kind=process
    transitions: List[StepTransition] = Field(default_factory=list)

    class Config:
        frozen = True
```

#### ExperienceSpec

```python
class ExperienceSpec(BaseModel):
    name: str
    title: Optional[str] = None
    start_step: str
    steps: List[ExperienceStep] = Field(default_factory=list)

    class Config:
        frozen = True

    def get_step(self, name: str) -> Optional[ExperienceStep]:
        ...
```

---

### Service Types

#### AuthKind

```python
class AuthKind(str, Enum):
    API_KEY_HEADER = "api_key_header"
    API_KEY_QUERY = "api_key_query"
    OAUTH2_PKCE = "oauth2_pkce"
    BASIC_AUTH = "basic_auth"
    BEARER_TOKEN = "bearer_token"
    CUSTOM = "custom"
```

#### AuthProfile

```python
class AuthProfile(BaseModel):
    kind: AuthKind
    options: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True
```

#### ServiceSpec

```python
class ServiceSpec(BaseModel):
    name: str
    title: Optional[str] = None
    spec_url: Optional[str] = None
    auth_profile: Optional[AuthProfile] = None
    owner: Optional[str] = None

    class Config:
        frozen = True
```

---

### Foreign Model Types

#### ForeignConstraintKind

```python
class ForeignConstraintKind(str, Enum):
    READ_ONLY = "read_only"
    EVENT_DRIVEN = "event_driven"
    BATCH_IMPORT = "batch_import"
```

#### ForeignConstraint

```python
class ForeignConstraint(BaseModel):
    kind: ForeignConstraintKind

    class Config:
        frozen = True
```

#### ForeignModelSpec

```python
class ForeignModelSpec(BaseModel):
    name: str
    title: Optional[str] = None
    service_ref: str
    key_fields: List[str] = Field(default_factory=list)
    fields: List[FieldSpec] = Field(default_factory=list)
    constraints: List[ForeignConstraint] = Field(default_factory=list)

    class Config:
        frozen = True
```

---

### Integration Types

#### IntegrationAction

```python
class IntegrationAction(BaseModel):
    name: str
    when_surface: str
    call_service: str
    call_operation: str
    call_mapping: Dict[str, str] = Field(default_factory=dict)
    response_entity: Optional[str] = None
    response_foreign_model: Optional[str] = None
    response_mapping: Dict[str, str] = Field(default_factory=dict)

    class Config:
        frozen = True
```

#### IntegrationSync

```python
class IntegrationSync(BaseModel):
    name: str
    mode: str  # "scheduled", "event_driven"
    schedule: Optional[str] = None
    from_service: str
    from_operation: str
    from_foreign_model: str
    into_entity: str
    match_rules: Dict[str, str] = Field(default_factory=dict)

    class Config:
        frozen = True
```

#### IntegrationSpec

```python
class IntegrationSpec(BaseModel):
    name: str
    title: Optional[str] = None
    service_refs: List[str] = Field(default_factory=list)
    foreign_model_refs: List[str] = Field(default_factory=list)
    actions: List[IntegrationAction] = Field(default_factory=list)
    syncs: List[IntegrationSync] = Field(default_factory=list)

    class Config:
        frozen = True

    def get_integration(self, name: str) -> Optional[IntegrationSpec]:
        ...
```

---

### Top-Level Types

#### AppSpec

```python
class AppSpec(BaseModel):
    """
    Complete application specification.

    This is the IR - the single source of truth for code generation.
    """
    name: str
    title: Optional[str] = None
    version: str = "0.1.0"
    domain: DomainSpec = Field(default_factory=DomainSpec)
    surfaces: List[SurfaceSpec] = Field(default_factory=list)
    experiences: List[ExperienceSpec] = Field(default_factory=list)
    services: List[ServiceSpec] = Field(default_factory=list)
    foreign_models: List[ForeignModelSpec] = Field(default_factory=list)
    integrations: List[IntegrationSpec] = Field(default_factory=list)

    class Config:
        frozen = True

    # Convenience methods
    def get_entity(self, name: str) -> Optional[EntitySpec]:
        return self.domain.get_entity(name)

    def get_surface(self, name: str) -> Optional[SurfaceSpec]:
        ...

    def get_experience(self, name: str) -> Optional[ExperienceSpec]:
        ...

    def get_service(self, name: str) -> Optional[ServiceSpec]:
        ...

    def get_foreign_model(self, name: str) -> Optional[ForeignModelSpec]:
        ...

    def get_integration(self, name: str) -> Optional[IntegrationSpec]:
        ...

    @property
    def type_catalog(self) -> Dict[str, List[FieldType]]:
        """
        Extract catalog of all field types.

        Returns mapping of field names to types they use.
        Useful for stack generators and type analysis.
        """
        ...

    def get_field_type_conflicts(self) -> List[str]:
        """Detect fields with same name but different types."""
        ...
```

#### ModuleFragment

```python
class ModuleFragment(BaseModel):
    """Fragment of an application spec from a single module."""
    entities: List[EntitySpec] = Field(default_factory=list)
    surfaces: List[SurfaceSpec] = Field(default_factory=list)
    experiences: List[ExperienceSpec] = Field(default_factory=list)
    services: List[ServiceSpec] = Field(default_factory=list)
    foreign_models: List[ForeignModelSpec] = Field(default_factory=list)
    integrations: List[IntegrationSpec] = Field(default_factory=list)

    class Config:
        frozen = True
```

#### ModuleIR

```python
class ModuleIR(BaseModel):
    """Complete IR for a single DSL module."""
    name: str             # e.g., "vat_tools.core"
    file: Path            # Source file path
    uses: List[str] = Field(default_factory=list)  # Dependencies
    fragment: ModuleFragment = Field(default_factory=ModuleFragment)

    class Config:
        frozen = True
```

---

## Examples

### Complete Entity

**DSL**:
```dsl
entity Invoice "Invoice":
  id: uuid pk
  client: ref Client required
  number: str(20) required
  total: decimal(10,2) required
  status: enum[draft,issued,paid]=draft
  issued_at: datetime
  created_at: datetime auto_add
  updated_at: datetime auto_update

  unique: client, number
  index: issued_at desc
```

**IR (Python)**:
```python
EntitySpec(
    name="Invoice",
    title="Invoice",
    fields=[
        FieldSpec(
            name="id",
            type=FieldType(kind=FieldTypeKind.UUID),
            modifiers=[FieldModifier.PK]
        ),
        FieldSpec(
            name="client",
            type=FieldType(kind=FieldTypeKind.REF, ref_entity="Client"),
            modifiers=[FieldModifier.REQUIRED]
        ),
        FieldSpec(
            name="number",
            type=FieldType(kind=FieldTypeKind.STR, max_length=20),
            modifiers=[FieldModifier.REQUIRED]
        ),
        FieldSpec(
            name="total",
            type=FieldType(kind=FieldTypeKind.DECIMAL, precision=10, scale=2),
            modifiers=[FieldModifier.REQUIRED]
        ),
        FieldSpec(
            name="status",
            type=FieldType(
                kind=FieldTypeKind.ENUM,
                enum_values=["draft", "issued", "paid"]
            ),
            default="draft"
        ),
        FieldSpec(
            name="issued_at",
            type=FieldType(kind=FieldTypeKind.DATETIME)
        ),
        FieldSpec(
            name="created_at",
            type=FieldType(kind=FieldTypeKind.DATETIME),
            modifiers=[FieldModifier.AUTO_ADD]
        ),
        FieldSpec(
            name="updated_at",
            type=FieldType(kind=FieldTypeKind.DATETIME),
            modifiers=[FieldModifier.AUTO_UPDATE]
        ),
    ],
    constraints=[
        Constraint(kind=ConstraintKind.UNIQUE, fields=["client", "number"]),
        Constraint(kind=ConstraintKind.INDEX, fields=["issued_at"])
    ]
)
```

**IR (JSON)**:
```json
{
  "name": "Invoice",
  "title": "Invoice",
  "fields": [
    {
      "name": "id",
      "type": {"kind": "uuid"},
      "modifiers": ["pk"],
      "default": null
    },
    {
      "name": "client",
      "type": {"kind": "ref", "ref_entity": "Client"},
      "modifiers": ["required"],
      "default": null
    },
    {
      "name": "total",
      "type": {"kind": "decimal", "precision": 10, "scale": 2},
      "modifiers": ["required"],
      "default": null
    },
    {
      "name": "status",
      "type": {"kind": "enum", "enum_values": ["draft", "issued", "paid"]},
      "modifiers": [],
      "default": "draft"
    }
  ],
  "constraints": [
    {"kind": "unique", "fields": ["client", "number"]},
    {"kind": "index", "fields": ["issued_at"]}
  ]
}
```

### Complete Surface

**DSL**:
```dsl
surface invoice_create "Create Invoice":
  uses entity Invoice
  mode: create

  section client_info "Client Information":
    field client "Client"
      help: "Select the client for this invoice"

  section details "Invoice Details":
    field number "Invoice Number"
      placeholder: "INV-2025-001"
    field total "Total Amount"
    field status "Status"

  action save "Create Invoice":
    outcome: surface invoice_detail
```

**IR**:
```python
SurfaceSpec(
    name="invoice_create",
    title="Create Invoice",
    entity_ref="Invoice",
    mode=SurfaceMode.CREATE,
    sections=[
        SurfaceSection(
            name="client_info",
            title="Client Information",
            elements=[
                SurfaceElement(
                    name="client",
                    label="Client",
                    help_text="Select the client for this invoice"
                )
            ]
        ),
        SurfaceSection(
            name="details",
            title="Invoice Details",
            elements=[
                SurfaceElement(
                    name="number",
                    label="Invoice Number",
                    placeholder="INV-2025-001"
                ),
                SurfaceElement(name="total", label="Total Amount"),
                SurfaceElement(name="status", label="Status"),
            ]
        ),
    ],
    actions=[
        SurfaceAction(
            name="save",
            label="Create Invoice",
            outcome=ActionOutcome(
                kind=OutcomeKind.SURFACE,
                target="invoice_detail"
            )
        )
    ]
)
```

---

## Working with the IR

### Creating IR Programmatically

```python
from dazzle.core import ir

# Build an entity
entity = ir.EntitySpec(
    name="Task",
    title="Task",
    fields=[
        ir.FieldSpec(
            name="id",
            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
            modifiers=[ir.FieldModifier.PK]
        ),
        ir.FieldSpec(
            name="title",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
            modifiers=[ir.FieldModifier.REQUIRED]
        ),
    ]
)

# Build AppSpec
appspec = ir.AppSpec(
    name="todo",
    domain=ir.DomainSpec(entities=[entity]),
    surfaces=[],
    experiences=[]
)

# Serialize to JSON
import json
print(json.dumps(appspec.model_dump(), indent=2))
```

### Querying the IR

```python
# Get entity
invoice = appspec.get_entity("Invoice")

# Get primary key
pk = invoice.primary_key  # → FieldSpec(name="id", ...)

# Get field
client_field = invoice.get_field("client")
if client_field and client_field.type.kind == ir.FieldTypeKind.REF:
    client_entity = appspec.get_entity(client_field.type.ref_entity)

# Check modifiers
if client_field.is_required:
    print("Client is required")
```

### Modifying the IR

Remember: IR is immutable!

```python
# ❌ This fails:
entity.name = "NewName"  # FrozenInstanceError

# ✅ Create new instance:
new_entity = entity.model_copy(update={"name": "NewName"})

# ✅ Or build new instance:
updated_appspec = ir.AppSpec(
    name=appspec.name,
    domain=ir.DomainSpec(
        entities=[new_entity] + appspec.domain.entities[1:]
    ),
    surfaces=appspec.surfaces,
    # ...
)
```

---

## Summary

The DAZZLE IR is:

- ✅ **Complete** - Represents entire application
- ✅ **Typed** - Pydantic validates everything
- ✅ **Immutable** - Thread-safe and predictable
- ✅ **Framework-agnostic** - Not tied to any technology
- ✅ **Serializable** - Can save/load as JSON
- ✅ **Self-documenting** - Rich properties and methods

**Implementation**: `src/dazzle/core/ir.py` (900+ lines)
**See also**:
- DSL Reference: `DAZZLE_DSL_REFERENCE_0_1.md`
- Parser: `src/dazzle/core/dsl_parser.py`
- Linker: `src/dazzle/core/linker.py`

---

**Last Updated**: 2025-11-23
**DAZZLE Version**: 0.1.0
