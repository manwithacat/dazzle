# Stack Generation Best Practices & Common Failure Modes

**Date**: 2025-11-25
**Purpose**: Prevent systematic bugs across all stack generators
**Audience**: Stack developers, code reviewers, DAZZLE maintainers

---

## Executive Summary

Analysis of the `nextjs_onebox` stack revealed **17 critical/high severity bugs**, many of which stem from **systematic issues** in how we generate code from the AppSpec IR. This document identifies common failure modes and proposes:

1. **Base generator improvements** - Shared utilities to prevent repetitive bugs
2. **Validation layers** - Automated checks before code generation
3. **Testing frameworks** - Systematic verification of generated code
4. **Design patterns** - Proven approaches for common generation tasks

**Key Insight**: Most bugs fall into 5 categories that can be prevented with better abstractions.

---

## Part 1: Common Failure Modes

### Category 1: Schema/Type Mismatches

**Symptom**: Generated code has inconsistent field names, types, or structures across layers.

**Examples from nextjs_onebox**:
- Issue #3: Prisma schema uses relations, TypeScript uses FK field names
- Issue #9: TypeScript types don't match Prisma schema
- Issue #12: Entity types missing index signatures for generic constraints
- Issue #13: Auth lib types don't match Prisma schema nullability

**Root Cause**: Each generator independently interprets the IR without coordination.

```
IR (AppSpec)
    ↓
    ├─→ Prisma Generator → schema.prisma (createdBy: User)
    ├─→ Types Generator  → entities.ts (createdBy: string)  ❌ Mismatch!
    └─→ Actions Generator → CRUD code expecting createdById  ❌ Fails!
```

**Impact**: Type errors, runtime failures, broken relations

---

### Category 2: Template Variable Interpolation Bugs

**Symptom**: Generated code contains incomplete expressions, empty values, or syntax errors.

**Examples from nextjs_onebox**:
- Issue #7: `defaultValue={}` (empty object)
- Issue #7: `defaultValue={item.` (incomplete property access)
- Issue #7: `defaultChecked={}` (should be boolean)

**Root Cause**: Template strings with conditional logic that doesn't handle all cases.

```python
# BUGGY PATTERN:
def generate_form_field(field, mode):
    if mode == "create":
        return f"<Input defaultValue={{{field.default}}} />"  # ❌ What if no default?
    elif mode == "edit":
        return f"<Input defaultValue={{item.{field.name}}} />"  # ❌ Wrong for FK fields!
```

**Impact**: Build failures, JSX syntax errors, runtime errors

---

### Category 3: Framework Version/API Mismatches

**Symptom**: Generated code uses APIs that don't exist in the specified framework version.

**Examples from nextjs_onebox**:
- Issue #5: `next.config.ts` not supported in Next.js 14 (only 15+)
- Issue #10: `useActionState` from React 19 used with React 18
- Issue #8: Tailwind classes used without color definitions
- Issue #11: String literals need `as const` for Prisma types

**Root Cause**: Stack generator doesn't track framework versions or API compatibility.

**Impact**: Build errors, runtime errors, cryptic warnings

---

### Category 4: Built-in vs Domain Model Collisions

**Symptom**: Stack provides built-in models (User, Session) that collide with DSL-defined entities.

**Examples from nextjs_onebox**:
- Issue #3: Duplicate User model (auth User + DSL User)
- Both use `@@map("users")` → table collision
- No strategy for merging vs renaming

**Root Cause**: No detection or resolution strategy for namespace conflicts.

```python
# BUGGY PATTERN:
def generate_schema():
    lines.append(built_in_user_model())  # Always emits User
    for entity in appspec.entities:
        lines.append(generate_model(entity))  # ❌ May also emit User!
```

**Impact**: Database errors, duplicate declarations, compilation failures

---

### Category 5: Relation/Foreign Key Handling

**Symptom**: ORM relations generated incorrectly or inconsistently.

**Examples from nextjs_onebox**:
- Issue #3: Relations without FK fields (`createdBy User` instead of `createdById + createdBy`)
- Issue #3: Missing inverse relations on target entities
- Issue #3: Multiple relations to same entity without names
- Issue #3: Indexes reference DSL field names instead of FK field names

**Root Cause**: Complex ORM rules not captured in generation logic.

**Prisma Requirements** (often violated):
```prisma
// ❌ WRONG: Just a relation field
model Ticket {
  createdBy User
}

// ✅ CORRECT: FK field + relation field
model Ticket {
  createdById String @db.Uuid
  createdBy   User   @relation("TicketCreatedBy", fields: [createdById], references: [id])
}

// ✅ Also need inverse relation on target:
model User {
  createdTickets Ticket[] @relation("TicketCreatedBy")
}
```

**Impact**: Schema validation errors, missing database constraints, broken joins

---

## Part 2: Recommended Solutions

### Solution 1: Canonical Type System (Base Generator)

**Problem**: Each generator independently maps IR types to framework types.

**Solution**: Create a **canonical intermediate format** that all generators consume.

```python
# src/dazzle/stacks/base/type_system.py

@dataclass
class CanonicalField:
    """Framework-agnostic field representation."""
    name: str                    # Original DSL name
    db_name: str                 # Database column name (snake_case)
    code_name: str               # Code variable name (camelCase)
    type_kind: ir.FieldTypeKind

    # For relations
    is_relation: bool = False
    fk_field_name: str | None = None      # e.g., "createdById"
    relation_field_name: str | None = None # e.g., "createdBy"
    target_entity: str | None = None
    relation_name: str | None = None      # For named relations

    # Type information
    db_type: str | None = None            # e.g., "UUID", "VARCHAR(200)"
    ts_type: str | None = None            # e.g., "string", "Date"
    python_type: str | None = None        # e.g., "str", "datetime"

    # Constraints
    is_required: bool
    is_unique: bool
    is_primary_key: bool
    default_value: Any | None = None

class TypeMapper:
    """Maps IR to canonical format with framework-specific outputs."""

    @staticmethod
    def from_ir_field(entity_name: str, field: ir.FieldSpec) -> CanonicalField:
        """Convert IR field to canonical format."""
        canonical = CanonicalField(
            name=field.name,
            db_name=to_snake_case(field.name),
            code_name=to_camel_case(field.name),
            type_kind=field.type.kind,
            is_required=field.is_required,
            is_unique=field.is_unique,
            is_primary_key=field.is_primary_key,
            default_value=field.default,
        )

        # Handle relations
        if field.type.kind == ir.FieldTypeKind.REF:
            canonical.is_relation = True
            canonical.fk_field_name = f"{canonical.code_name}Id"
            canonical.relation_field_name = canonical.code_name
            canonical.target_entity = field.type.ref_entity
            canonical.relation_name = f"{entity_name}{field.name.title()}"

        # Map to framework types
        canonical.db_type = TypeMapper.to_prisma_type(field)
        canonical.ts_type = TypeMapper.to_typescript_type(field)
        canonical.python_type = TypeMapper.to_python_type(field)

        return canonical

    @staticmethod
    def to_prisma_type(field: ir.FieldSpec) -> str:
        """Map to Prisma type."""
        # Single source of truth for Prisma types
        ...

    @staticmethod
    def to_typescript_type(field: ir.FieldSpec) -> str:
        """Map to TypeScript type."""
        # Single source of truth for TS types
        ...
```

**Benefits**:
- ✅ **Single source of truth** for type mappings
- ✅ **Consistent naming** across all generated code
- ✅ **Relation fields automatically computed** (FK + relation pairs)
- ✅ **Framework types derived systematically**

**Usage in generators**:
```python
class PrismaGenerator(Generator):
    def generate_field(self, entity_name: str, field: ir.FieldSpec) -> str:
        canonical = TypeMapper.from_ir_field(entity_name, field)

        if canonical.is_relation:
            # Generate FK field
            fk = f"{canonical.fk_field_name} {canonical.db_type}"
            # Generate relation field
            rel = f'{canonical.relation_field_name} {canonical.target_entity} @relation(...)'
            return fk, rel
        else:
            return f"{canonical.code_name} {canonical.db_type}"
```

---

### Solution 2: Template Validation Layer

**Problem**: Templates produce invalid code when variables are missing or wrong type.

**Solution**: **Validated template system** with type-safe substitutions.

```python
# src/dazzle/stacks/base/templates.py

from typing import TypedDict, Literal

class FormFieldContext(TypedDict):
    """Type-safe context for form field templates."""
    field_name: str
    field_type: Literal["text", "number", "boolean", "select", "date"]
    default_value: str  # Always a valid JavaScript expression
    placeholder: str
    label: str
    required: bool

class SafeTemplate:
    """Template with validation and safe defaults."""

    def __init__(self, template_str: str, required_vars: set[str]):
        self.template = template_str
        self.required_vars = required_vars

    def render(self, context: dict) -> str:
        """Render with validation."""
        # Check required variables
        missing = self.required_vars - set(context.keys())
        if missing:
            raise TemplateError(f"Missing required variables: {missing}")

        # Validate types
        for key, value in context.items():
            if value is None:
                raise TemplateError(f"Variable '{key}' cannot be None")

        return self.template.format(**context)

# Predefined safe templates
FORM_FIELD_TEMPLATES = {
    "create_text": SafeTemplate(
        '<Input name="{field_name}" defaultValue="{default_value}" placeholder="{placeholder}" required={{{required}}} />',
        required_vars={"field_name", "default_value", "placeholder", "required"}
    ),
    "edit_text": SafeTemplate(
        '<Input name="{field_name}" defaultValue={{item.{field_name} ?? "{default_value}"}} required={{{required}}} />',
        required_vars={"field_name", "default_value", "required"}
    ),
    "create_boolean": SafeTemplate(
        '<input type="checkbox" name="{field_name}" defaultChecked={{{default_value}}} />',
        required_vars={"field_name", "default_value"}  # default_value must be "true" or "false"
    ),
}

def generate_form_field(field: CanonicalField, mode: Literal["create", "edit"]) -> str:
    """Generate form field with validated templates."""

    # Build type-safe context
    context: FormFieldContext = {
        "field_name": field.code_name,
        "field_type": map_to_input_type(field.type_kind),
        "default_value": format_js_default(field.default_value, field.ts_type),  # Always valid JS
        "placeholder": field.name.replace("_", " ").title(),
        "label": field.name.replace("_", " ").title(),
        "required": field.is_required,
    }

    # Select template
    template_key = f"{mode}_{context['field_type']}"
    template = FORM_FIELD_TEMPLATES[template_key]

    # Render safely
    return template.render(context)

def format_js_default(value: Any, ts_type: str) -> str:
    """Format default value as valid JavaScript expression."""
    if value is None:
        if ts_type == "boolean":
            return "false"
        elif ts_type in ("number", "bigint"):
            return "0"
        else:
            return '""'  # Empty string for text

    if ts_type == "boolean":
        return "true" if value else "false"
    elif ts_type in ("number", "bigint"):
        return str(value)
    else:
        return f'"{value}"'  # Quote strings
```

**Benefits**:
- ✅ **No empty expressions** (`defaultValue={}` impossible)
- ✅ **Type-safe context** (TypedDict catches errors at dev time)
- ✅ **Required variables enforced**
- ✅ **Consistent formatting** (booleans always lowercase, strings quoted)

---

### Solution 3: Framework Version Manager

**Problem**: Generators don't track what versions of dependencies they target.

**Solution**: **Version-aware generation** with compatibility checks.

```python
# src/dazzle/stacks/base/framework_versions.py

@dataclass
class FrameworkVersion:
    """Framework version specification."""
    name: str
    version: str

    def __ge__(self, other: str) -> bool:
        """Compare versions."""
        from packaging import version
        return version.parse(self.version) >= version.parse(other)

@dataclass
class StackDependencies:
    """Stack dependency requirements."""
    react: FrameworkVersion
    next: FrameworkVersion | None = None
    typescript: FrameworkVersion | None = None
    prisma: FrameworkVersion | None = None
    tailwind: FrameworkVersion | None = None

class FrameworkFeatures:
    """Feature availability based on framework versions."""

    @staticmethod
    def supports_ts_config(next_version: FrameworkVersion) -> bool:
        """Check if Next.js supports next.config.ts."""
        return next_version >= "15.0.0"

    @staticmethod
    def has_use_action_state(react_version: FrameworkVersion) -> bool:
        """Check if React has useActionState."""
        return react_version >= "19.0.0"

    @staticmethod
    def get_form_state_import(react_version: FrameworkVersion) -> str:
        """Get correct import for form state hook."""
        if react_version >= "19.0.0":
            return 'import { useActionState } from "react";'
        else:
            return 'import { useFormState } from "react-dom";'

class NextJsOneboxStack(ModularBackend):
    """Next.js Onebox stack with version management."""

    def get_dependencies(self) -> StackDependencies:
        """Define stack dependencies."""
        return StackDependencies(
            react=FrameworkVersion("react", "18.3.1"),  # Using React 18
            next=FrameworkVersion("next", "14.2.0"),
            typescript=FrameworkVersion("typescript", "5.3.0"),
            prisma=FrameworkVersion("prisma", "5.20.0"),
            tailwind=FrameworkVersion("tailwindcss", "3.4.0"),
        )

    def generate_config(self) -> str:
        """Generate framework config based on version."""
        deps = self.get_dependencies()

        if FrameworkFeatures.supports_ts_config(deps.next):
            return self.generate_ts_config()
        else:
            return self.generate_mjs_config()  # Use .mjs for Next 14

    def generate_form_imports(self) -> str:
        """Generate imports based on React version."""
        deps = self.get_dependencies()
        return FrameworkFeatures.get_form_state_import(deps.react)
```

**Benefits**:
- ✅ **Version conflicts impossible** (checked at generation time)
- ✅ **API compatibility guaranteed**
- ✅ **Easy version upgrades** (change in one place)
- ✅ **Clear dependency requirements**

---

### Solution 4: Built-in Model Registry

**Problem**: No strategy for detecting/resolving conflicts between stack built-ins and DSL entities.

**Solution**: **Model registry** with conflict resolution strategies.

```python
# src/dazzle/stacks/base/model_registry.py

from enum import Enum
from typing import Protocol

class ConflictStrategy(Enum):
    """How to handle built-in vs DSL model conflicts."""
    MERGE = "merge"           # Merge DSL fields into built-in
    RENAME_BUILTIN = "rename" # Rename built-in (e.g., User → AuthUser)
    ERROR = "error"           # Fail with error message
    SKIP_BUILTIN = "skip"     # Don't generate built-in

@dataclass
class BuiltInModel:
    """A model provided by the stack."""
    name: str
    fields: list[CanonicalField]
    purpose: str  # e.g., "authentication", "audit_log"
    conflict_strategy: ConflictStrategy
    required: bool  # Can this be skipped?

class ModelRegistry:
    """Tracks built-in and DSL models, resolves conflicts."""

    def __init__(self):
        self.built_ins: dict[str, BuiltInModel] = {}
        self.dsl_models: dict[str, ir.EntitySpec] = {}
        self.resolved: dict[str, ResolvedModel] = {}

    def register_builtin(self, model: BuiltInModel):
        """Register a stack-provided model."""
        self.built_ins[model.name.lower()] = model

    def register_dsl_entities(self, entities: list[ir.EntitySpec]):
        """Register DSL entities."""
        for entity in entities:
            self.dsl_models[entity.name.lower()] = entity

    def resolve_conflicts(self) -> dict[str, ResolvedModel]:
        """Detect and resolve name conflicts."""
        conflicts = set(self.built_ins.keys()) & set(self.dsl_models.keys())

        for name in conflicts:
            builtin = self.built_ins[name]
            dsl = self.dsl_models[name]

            if builtin.conflict_strategy == ConflictStrategy.MERGE:
                self.resolved[name] = self._merge_models(builtin, dsl)
            elif builtin.conflict_strategy == ConflictStrategy.RENAME_BUILTIN:
                # Rename built-in to avoid collision
                new_name = f"{builtin.purpose.title()}{name.title()}"
                self.resolved[new_name] = ResolvedModel.from_builtin(builtin)
                self.resolved[name] = ResolvedModel.from_dsl(dsl)
            elif builtin.conflict_strategy == ConflictStrategy.ERROR:
                raise ConflictError(
                    f"Entity '{name}' conflicts with required built-in model. "
                    f"Please rename your entity."
                )
            elif builtin.conflict_strategy == ConflictStrategy.SKIP_BUILTIN:
                if builtin.required:
                    raise ConflictError(f"Cannot skip required built-in '{name}'")
                self.resolved[name] = ResolvedModel.from_dsl(dsl)

        # Add non-conflicting models
        for name, builtin in self.built_ins.items():
            if name not in conflicts:
                self.resolved[name] = ResolvedModel.from_builtin(builtin)

        for name, dsl in self.dsl_models.items():
            if name not in conflicts:
                self.resolved[name] = ResolvedModel.from_dsl(dsl)

        return self.resolved

    def _merge_models(self, builtin: BuiltInModel, dsl: ir.EntitySpec) -> ResolvedModel:
        """Merge DSL fields into built-in model."""
        # Start with built-in fields
        merged_fields = list(builtin.fields)

        # Add DSL fields (skip duplicates)
        builtin_names = {f.name.lower() for f in builtin.fields}
        for dsl_field in dsl.fields:
            if dsl_field.name.lower() not in builtin_names:
                canonical = TypeMapper.from_ir_field(dsl.name, dsl_field)
                merged_fields.append(canonical)

        return ResolvedModel(
            name=builtin.name,
            fields=merged_fields,
            source="merged",
            original_builtin=builtin,
            original_dsl=dsl,
        )

# Usage in stack
class NextJsOneboxStack(ModularBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = ModelRegistry()

        # Register built-in models
        self.registry.register_builtin(BuiltInModel(
            name="User",
            fields=[...],  # Auth fields
            purpose="authentication",
            conflict_strategy=ConflictStrategy.MERGE,  # Merge with DSL User
            required=True,
        ))

        self.registry.register_builtin(BuiltInModel(
            name="Session",
            fields=[...],
            purpose="authentication",
            conflict_strategy=ConflictStrategy.ERROR,  # Don't allow DSL Session
            required=True,
        ))

    def generate(self):
        # Register DSL entities
        self.registry.register_dsl_entities(self.spec.domain.entities)

        # Resolve conflicts
        models = self.registry.resolve_conflicts()

        # Generate from resolved models
        for model in models.values():
            self.generate_model(model)
```

**Benefits**:
- ✅ **Conflicts detected automatically**
- ✅ **Clear resolution strategy** per model
- ✅ **Merge logic centralized**
- ✅ **Extensible** for new built-ins

---

### Solution 5: Relation Graph Builder

**Problem**: Complex relation rules (FK fields, named relations, inverse relations) error-prone.

**Solution**: **Relation graph** that computes all relation metadata upfront.

```python
# src/dazzle/stacks/base/relation_graph.py

@dataclass
class Relation:
    """A relation between two entities."""
    source_entity: str
    source_field: str
    target_entity: str

    # Computed metadata
    fk_field_name: str          # e.g., "createdById"
    relation_field_name: str     # e.g., "createdBy"
    relation_name: str           # e.g., "TicketCreatedBy"
    inverse_field_name: str      # e.g., "createdTickets"

    # Properties
    is_required: bool
    is_unique: bool  # One-to-one vs one-to-many

class RelationGraph:
    """Builds complete relation metadata from IR."""

    def __init__(self, entities: list[ir.EntitySpec]):
        self.entities = {e.name: e for e in entities}
        self.relations: list[Relation] = []
        self.inverse_relations: dict[str, list[Relation]] = {}  # target -> [relations]

        self._build_graph()

    def _build_graph(self):
        """Extract all relations from entities."""
        for entity in self.entities.values():
            for field in entity.fields:
                if field.type.kind == ir.FieldTypeKind.REF:
                    relation = self._create_relation(entity.name, field)
                    self.relations.append(relation)

                    # Track inverse
                    target = relation.target_entity
                    if target not in self.inverse_relations:
                        self.inverse_relations[target] = []
                    self.inverse_relations[target].append(relation)

    def _create_relation(self, entity_name: str, field: ir.FieldSpec) -> Relation:
        """Create relation metadata."""
        target = field.type.ref_entity

        # Generate unique relation name
        relation_name = self._generate_relation_name(entity_name, field.name, target)

        # Generate inverse field name
        inverse_name = self._generate_inverse_name(entity_name, field.name, target)

        return Relation(
            source_entity=entity_name,
            source_field=field.name,
            target_entity=target,
            fk_field_name=f"{to_camel_case(field.name)}Id",
            relation_field_name=to_camel_case(field.name),
            relation_name=relation_name,
            inverse_field_name=inverse_name,
            is_required=field.is_required,
            is_unique=field.is_unique,
        )

    def _generate_relation_name(self, source: str, field: str, target: str) -> str:
        """Generate unique relation name."""
        # Count how many relations from source to target
        count = sum(
            1 for r in self.relations
            if r.source_entity == source and r.target_entity == target
        )

        if count > 0:
            # Multiple relations to same target, need unique names
            return f"{source}{field.title()}"
        else:
            # Single relation, simple name
            return f"{source}{target}"

    def _generate_inverse_name(self, source: str, field: str, target: str) -> str:
        """Generate inverse field name on target entity."""
        # Pluralize source entity name
        plural = f"{to_camel_case(field)}{source}s"
        return plural

    def get_relations_for_entity(self, entity_name: str) -> list[Relation]:
        """Get all outgoing relations from an entity."""
        return [r for r in self.relations if r.source_entity == entity_name]

    def get_inverse_relations(self, entity_name: str) -> list[Relation]:
        """Get all incoming relations to an entity."""
        return self.inverse_relations.get(entity_name, [])

# Usage in Prisma generator
class PrismaGenerator(Generator):
    def generate(self):
        # Build relation graph once
        self.relation_graph = RelationGraph(self.spec.domain.entities)

        # Generate models
        for entity in self.spec.domain.entities:
            self.generate_model(entity)

    def generate_model(self, entity: ir.EntitySpec):
        lines = [f"model {entity.name} {{"]

        # Regular fields + FK fields
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF:
                # Find relation metadata
                relation = next(
                    r for r in self.relation_graph.get_relations_for_entity(entity.name)
                    if r.source_field == field.name
                )
                # Generate FK field
                lines.append(f"  {relation.fk_field_name} String @db.Uuid")
            else:
                lines.append(self.generate_regular_field(field))

        # Relation fields
        for relation in self.relation_graph.get_relations_for_entity(entity.name):
            lines.append(
                f'  {relation.relation_field_name} {relation.target_entity} '
                f'@relation("{relation.relation_name}", fields: [{relation.fk_field_name}], references: [id])'
            )

        # Inverse relations
        for relation in self.relation_graph.get_inverse_relations(entity.name):
            lines.append(
                f'  {relation.inverse_field_name} {relation.source_entity}[] '
                f'@relation("{relation.relation_name}")'
            )

        return "\n".join(lines) + "}"
```

**Benefits**:
- ✅ **All relation metadata computed once**
- ✅ **Consistent naming** (no duplicates)
- ✅ **Inverse relations automatic**
- ✅ **Named relations for multiple refs**
- ✅ **Reusable across generators** (Prisma, TypeScript, SQL migrations)

---

## Part 3: Testing & Validation Framework

### Automated Build Verification

**Problem**: Bugs only discovered when users try to build generated code.

**Solution**: **Integration tests** that build and type-check every example.

```python
# tests/integration/test_stack_builds.py

import subprocess
from pathlib import Path
import pytest

STACKS = ["django_micro_modular", "nextjs_onebox", "express_micro"]
EXAMPLES = ["simple_task", "support_tickets"]

@pytest.mark.parametrize("stack,example", [
    (stack, example) for stack in STACKS for example in EXAMPLES
])
def test_stack_builds(stack: str, example: str, tmp_path: Path):
    """Test that generated code builds without errors."""

    # Generate project
    result = subprocess.run(
        ["dazzle", "example", example, "--stack", stack, "--path", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Example creation failed: {result.stderr}"

    # Navigate to build output
    build_dir = tmp_path / "build" / example

    # Run stack-specific build verification
    if stack == "nextjs_onebox":
        verify_nextjs_build(build_dir)
    elif stack == "django_micro_modular":
        verify_django_build(build_dir)
    elif stack == "express_micro":
        verify_express_build(build_dir)

def verify_nextjs_build(build_dir: Path):
    """Verify Next.js project builds."""

    # Install dependencies
    subprocess.run(["npm", "install"], cwd=build_dir, check=True)

    # Type check
    result = subprocess.run(
        ["npx", "tsc", "--noEmit"],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Type errors:\n{result.stdout}"

    # Lint
    result = subprocess.run(
        ["npm", "run", "lint"],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Lint errors:\n{result.stdout}"

    # Prisma validate
    result = subprocess.run(
        ["npx", "prisma", "validate"],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Prisma schema invalid:\n{result.stderr}"

    # Prisma generate (creates client)
    result = subprocess.run(
        ["npx", "prisma", "generate"],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Prisma generate failed:\n{result.stderr}"

    # Build
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stdout}"
```

---

### Schema Validation

**Problem**: Generated schemas (Prisma, SQL, GraphQL) may be syntactically invalid.

**Solution**: **Parse and validate** schemas as part of generation.

```python
# src/dazzle/stacks/base/schema_validator.py

from typing import Protocol

class SchemaValidator(Protocol):
    """Interface for schema validators."""

    def validate(self, schema: str) -> list[str]:
        """Validate schema, return list of errors."""
        ...

class PrismaValidator:
    """Validates Prisma schemas."""

    def validate(self, schema: str) -> list[str]:
        """Run prisma validate."""
        import tempfile
        import subprocess

        errors = []

        with tempfile.TemporaryDirectory() as tmpdir:
            schema_path = Path(tmpdir) / "schema.prisma"
            schema_path.write_text(schema)

            result = subprocess.run(
                ["npx", "prisma", "validate", "--schema", str(schema_path)],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                errors.append(result.stderr)

        return errors

# In generator
class PrismaGenerator(Generator):
    def generate(self) -> GeneratorResult:
        result = GeneratorResult()

        schema = self._build_schema()

        # Validate before writing
        validator = PrismaValidator()
        errors = validator.validate(schema)
        if errors:
            raise GenerationError(f"Invalid Prisma schema:\n" + "\n".join(errors))

        # Write only if valid
        path = self.output_dir / "prisma" / "schema.prisma"
        self._write_file(path, schema)

        return result
```

---

## Part 4: Implementation Roadmap

### Phase 1: Foundation (Week 1)

**Base Generator Improvements**:
1. Create `TypeMapper` with canonical field representation
2. Create `FrameworkVersion` manager
3. Create `SafeTemplate` system with validation
4. Add schema validators (Prisma, TypeScript)

**Tests**:
1. Unit tests for TypeMapper
2. Unit tests for version compatibility checks
3. Unit tests for template validation

### Phase 2: Relation System (Week 2)

**Relation Graph**:
1. Implement `RelationGraph` builder
2. Update Prisma generator to use relation graph
3. Update TypeScript types generator
4. Update Actions generator

**Tests**:
1. Test relation graph with complex scenarios
2. Test multiple relations to same entity
3. Test inverse relation generation

### Phase 3: Model Registry (Week 2-3)

**Built-in Models**:
1. Implement `ModelRegistry`
2. Update nextjs_onebox to use registry
3. Add conflict resolution strategies
4. Document built-in model system

**Tests**:
1. Test User model merging
2. Test conflict detection
3. Test rename strategy

### Phase 4: Integration Testing (Week 3-4)

**Test Framework**:
1. Set up integration test suite
2. Add build verification for all stacks
3. Add golden master tests (snapshot testing)
4. Set up CI/CD to run on every PR

**Coverage**:
1. Test all stack + example combinations
2. Test edge cases (empty entities, complex relations)
3. Test version upgrades

### Phase 5: Documentation (Week 4)

**Developer Docs**:
1. Stack development guide using new base generators
2. Testing guide
3. Troubleshooting guide
4. Migration guide for existing stacks

---

## Part 5: Immediate Actions (Critical Fixes)

### Must Do Now (Before Next Release)

1. **Fix nextjs_onebox critical bugs**:
   - ✅ Prisma schema (completed)
   - next.config.mjs
   - JSX syntax in forms
   - TypeScript types matching Prisma
   - Tailwind colors

2. **Add integration tests**:
   - Test simple_task + support_tickets with nextjs_onebox
   - Verify builds succeed
   - Verify type checking passes

3. **Document known issues**:
   - Add KNOWN_ISSUES.md to nextjs_onebox
   - Mark as "beta" in README
   - Add troubleshooting guide

### Quick Wins (Low-Hanging Fruit)

1. **Extract TypeMapper to base**:
   - Move type mapping logic to `src/dazzle/stacks/base/types.py`
   - Update nextjs_onebox to use it
   - Document usage

2. **Add Prisma validation**:
   - Run `prisma validate` after schema generation
   - Fail fast with clear error messages

3. **Standardize naming conventions**:
   - Document snake_case → camelCase rules
   - Document pluralization rules
   - Provide utility functions

---

## Part 6: Metrics & Success Criteria

### How We'll Know It's Working

**Metrics to Track**:
1. **Generated Code Build Success Rate**: % of generated projects that build without manual fixes
2. **Type Errors**: Count of TypeScript/Python type errors in generated code
3. **Schema Validity**: % of generated schemas that pass validation
4. **User-Reported Bugs**: Number of generation bugs reported per stack per month

**Success Criteria** (6 months):
- ✅ 95%+ build success rate
- ✅ Zero type errors in generated code
- ✅ 100% schema validity
- ✅ < 1 generation bug per stack per month

**Current Baseline** (nextjs_onebox):
- ❌ 0% build success rate (17 critical bugs)
- ❌ ~15 type errors
- ❌ Schema validation fails
- ❌ 17 bugs in first user trial

---

## Conclusion

The bugs in `nextjs_onebox` are **symptoms of systematic issues** in how we generate code. By addressing the 5 core failure modes with shared abstractions, we can:

1. **Prevent entire classes of bugs** across all stacks
2. **Reduce development time** for new stacks (reuse base generators)
3. **Improve code quality** through validation and testing
4. **Build user trust** with reliable code generation

**Next Steps**:
1. Review this document with team
2. Prioritize which solutions to implement first
3. Create tickets for each phase
4. Start with TypeMapper (highest impact, used by all generators)

**Questions for Discussion**:
1. Which failure mode is most critical to address first?
2. Should we pause new stack development to fix the base generators?
3. What's our strategy for migrating existing stacks to new base system?
4. How do we prevent regressions as we refactor?

---

**Document Status**: Draft for Review
**Author**: Analysis from nextjs_onebox bug report
**Last Updated**: 2025-11-25
