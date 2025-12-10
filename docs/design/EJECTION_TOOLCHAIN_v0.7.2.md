# DAZZLE Ejection Toolchain Spec (v0.7.2)

> **Version**: 0.7.2
> **Status**: Draft
> **Author**: Claude + James
> **Date**: 2025-12-10

---

## 1. Executive Summary

The Ejection Toolchain provides a path from **DNR runtime** to **standalone generated code** when projects outgrow the native runtime or have deployment constraints that require traditional application structure.

### Core Principle

```
DNR Runtime (default)     →     Ejected Code (optional)
─────────────────────────────────────────────────────────
Fast iteration                  Full customization
Zero config                     Framework-specific
Live from DSL                   Traditional deployment
```

**Key Insight**: DNR remains the primary development experience. Ejection is an escape hatch for production scenarios requiring:
- Custom infrastructure (non-Docker deployments)
- Framework-specific integrations (Django admin, Next.js SSR)
- Performance optimization beyond DNR's generalist approach
- Regulatory/compliance requirements for auditable code

---

## 2. When to Eject

### Eject When:
- Deploying to infrastructure that can't run Docker/DNR
- Needing deep integration with framework-specific features
- Performance profiling reveals DNR overhead is unacceptable
- Compliance requires auditable, version-controlled application code
- Team expertise is stronger in a specific framework

### Don't Eject When:
- Still iterating on requirements (stay in DNR)
- Simple CRUD applications (DNR is sufficient)
- Prototyping or MVPs (DNR is faster)
- No specific framework requirement exists

---

## 3. Configuration

### 3.1 Extend dazzle.toml (Not Separate File)

Ejection configuration lives in the existing `dazzle.toml` project file:

```toml
[project]
name = "my_app"
version = "1.0.0"

[dsl]
paths = ["dsl/"]

[runtime]
default = "dnr"  # "dnr" or "ejected"

# Optional: Only required when ejecting
[ejection]
enabled = false  # Set to true to enable ejection commands

[ejection.backend]
framework = "fastapi"      # fastapi | django | flask (future)
models = "pydantic-v2"     # pydantic-v2 | sqlalchemy | django-orm (future)
async = true
routing = "router-modules" # router-modules | flat

[ejection.frontend]
framework = "react"        # react | vue | nextjs (future)
api_client = "zod-fetch"   # zod-fetch | openapi-ts | axios (future)
state = "tanstack-query"   # tanstack-query | swr | none

[ejection.testing]
contract = "schemathesis"  # schemathesis | none
unit = "pytest"            # pytest | unittest
e2e = "playwright"         # playwright | none

[ejection.ci]
template = "github-actions" # github-actions | gitlab-ci | none

[ejection.output]
directory = "generated/"   # Output directory for ejected code
clean = true               # Clean output directory before generation
```

### 3.2 Defaults

When `[ejection]` section is absent or `enabled = false`, use these defaults:

```python
EJECTION_DEFAULTS = {
    "backend": {
        "framework": "fastapi",
        "models": "pydantic-v2",
        "async": True,
        "routing": "router-modules",
    },
    "frontend": {
        "framework": "react",
        "api_client": "zod-fetch",
        "state": "tanstack-query",
    },
    "testing": {
        "contract": "schemathesis",
        "unit": "pytest",
        "e2e": "none",
    },
    "ci": {
        "template": "github-actions",
    },
    "output": {
        "directory": "generated/",
        "clean": True,
    },
}
```

---

## 4. CLI Commands

### 4.1 Primary Command

```bash
# Eject to standalone code
dazzle eject

# Eject with specific backend only
dazzle eject --backend

# Eject with specific frontend only
dazzle eject --frontend

# Eject with dry-run (show what would be generated)
dazzle eject --dry-run

# Eject to specific directory
dazzle eject --output ./my-app/

# Eject and override framework
dazzle eject --backend-framework django
```

### 4.2 Inspection Commands

```bash
# Show ejection configuration
dazzle eject config

# Show what files would be generated
dazzle eject plan

# Validate ejection configuration
dazzle eject validate
```

### 4.3 Post-Ejection Commands

```bash
# After ejection, use standard tools
cd generated/
pip install -r requirements.txt
uvicorn backend.app:app --reload

# Or with frontend
cd generated/frontend
npm install
npm run dev
```

---

## 5. Architecture

### 5.1 Generation Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        dazzle eject                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EjectionConfig                              │
│  (parsed from dazzle.toml [ejection] section)                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                        AppSpec                                   │
│  (from DSL parser - includes all v0.7.x business logic)         │
│  - Entities with fields, relationships, state machines          │
│  - Computed fields, invariants, access rules                    │
│  - Surfaces, workspaces, personas                               │
│  - Archetypes, intents, examples (v0.7.1)                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┬───────────────┐
          ▼               ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Backend  │    │ Frontend │    │ Testing  │    │    CI    │
    │ Adapter  │    │ Adapter  │    │ Adapter  │    │ Adapter  │
    └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘
         │               │               │               │
         ▼               ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Python   │    │ TypeScript│   │ pytest   │    │ ci.yml   │
    │ Code     │    │ Code     │    │ Stubs    │    │          │
    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 5.2 Key Design Decision: AppSpec as Source (Not OpenAPI)

**Why AppSpec, not OpenAPI?**

OpenAPI is a REST API description format. It cannot represent:
- State machines with guards (`transitions:`)
- Computed fields (`computed sum(items.amount)`)
- Invariants (`invariant: end_date > start_date`)
- Access rules (`access: read: owner = current_user`)
- Archetypes and inheritance (`extends: Timestamped`)
- Intent declarations (`intent: "Track customer orders"`)
- Example data (`examples: [{...}]`)
- Relationship semantics (`has_many`, `embeds`, `belongs_to`)

**Solution**: Generate directly from AppSpec. OpenAPI is generated as a **parallel artifact** for API documentation, not as an intermediate representation.

```
AppSpec ──┬──→ Backend Code (includes business logic)
          ├──→ Frontend Code (types, validation, hooks)
          ├──→ Test Stubs (with invariant checks)
          ├──→ OpenAPI Spec (documentation only)
          └──→ CI Config
```

---

## 6. Output Structure

### 6.1 Canonical Directory Layout

```
generated/
├── README.md                    # Getting started guide
├── pyproject.toml               # Python project config
├── package.json                 # Frontend dependencies
│
├── spec/
│   ├── openapi.yaml             # Generated OpenAPI (docs only)
│   └── json/                    # JSON Schema per entity
│       ├── Task.schema.json
│       └── User.schema.json
│
├── backend/
│   ├── __init__.py
│   ├── app.py                   # FastAPI application entry
│   ├── config.py                # Environment configuration
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py              # Base model with common fields
│   │   ├── task.py              # Task entity model
│   │   └── user.py              # User entity model
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── task.py              # Pydantic schemas (create/update/read)
│   │   └── user.py
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── task.py              # Task CRUD endpoints
│   │   └── user.py              # User CRUD endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── task.py              # Task business logic
│   │   └── user.py              # User business logic
│   │
│   ├── guards/                  # Generated from state machines
│   │   ├── __init__.py
│   │   └── task_transitions.py  # Task state transition guards
│   │
│   ├── validators/              # Generated from invariants
│   │   ├── __init__.py
│   │   └── task_invariants.py   # Task invariant checks
│   │
│   └── access/                  # Generated from access rules
│       ├── __init__.py
│       └── policies.py          # Row-level security policies
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   │
│   └── src/
│       ├── api/
│       │   ├── client.ts        # HTTP client with validation
│       │   ├── types.ts         # TypeScript types from entities
│       │   ├── schemas.ts       # Zod schemas for validation
│       │   └── hooks.ts         # TanStack Query hooks
│       │
│       └── lib/
│           └── validation.ts    # Client-side invariant checks
│
├── tests/
│   ├── conftest.py              # pytest configuration
│   │
│   ├── contract/
│   │   └── test_openapi.py      # Schemathesis contract tests
│   │
│   ├── unit/
│   │   ├── test_task_crud.py    # Task CRUD tests
│   │   ├── test_task_states.py  # State machine tests
│   │   └── test_task_invariants.py  # Invariant tests
│   │
│   └── e2e/                     # Playwright tests (if enabled)
│       └── test_task_flow.py
│
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions workflow
│
├── Dockerfile                   # Multi-stage Docker build
├── docker-compose.yml           # Local development
└── .env.example                 # Environment template
```

---

## 7. Backend Adapters

### 7.1 Adapter Interface

All backend adapters implement the existing `Generator` interface:

```python
# src/dazzle/eject/adapters/base.py
from abc import ABC, abstractmethod
from dazzle.eject.generator import Generator, GeneratorResult
from dazzle.core.ir import AppSpec

class BackendAdapter(Generator, ABC):
    """Base class for backend code generators."""

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        config: EjectionBackendConfig,
    ):
        super().__init__(spec, output_dir)
        self.config = config

    @abstractmethod
    def generate_models(self) -> GeneratorResult:
        """Generate entity models."""
        pass

    @abstractmethod
    def generate_schemas(self) -> GeneratorResult:
        """Generate request/response schemas."""
        pass

    @abstractmethod
    def generate_routers(self) -> GeneratorResult:
        """Generate API routers/endpoints."""
        pass

    @abstractmethod
    def generate_services(self) -> GeneratorResult:
        """Generate business logic services."""
        pass

    @abstractmethod
    def generate_guards(self) -> GeneratorResult:
        """Generate state machine transition guards."""
        pass

    @abstractmethod
    def generate_validators(self) -> GeneratorResult:
        """Generate invariant validators."""
        pass

    @abstractmethod
    def generate_access(self) -> GeneratorResult:
        """Generate access control policies."""
        pass
```

### 7.2 FastAPI Adapter (Initial Implementation)

```python
# src/dazzle/eject/adapters/fastapi.py
from .base import BackendAdapter

class FastAPIAdapter(BackendAdapter):
    """Generate FastAPI application from AppSpec."""

    def generate(self) -> GeneratorResult:
        """Generate complete FastAPI application."""
        result = GeneratorResult()

        # Generate in dependency order
        result.merge(self.generate_models())
        result.merge(self.generate_schemas())
        result.merge(self.generate_guards())
        result.merge(self.generate_validators())
        result.merge(self.generate_access())
        result.merge(self.generate_services())
        result.merge(self.generate_routers())
        result.merge(self.generate_app())

        return result
```

### 7.3 Business Logic Generation

Unlike the original spec's "no business logic" approach, ejected code **includes** all business logic from the DSL:

#### State Machine Guards

From DSL:
```dsl
entity Ticket "Ticket":
  status: enum[open,assigned,resolved,closed] = open
  assigned_to: ref User
  resolution: text

  transitions:
    open -> assigned: requires assigned_to
    assigned -> resolved: requires resolution
    resolved -> closed
    closed -> open: role(admin)
```

Generated (`backend/guards/ticket_transitions.py`):
```python
"""
State machine guards for Ticket entity.
Generated from DSL - DO NOT EDIT.
"""
from ..models.ticket import Ticket, TicketStatus
from ..access.context import RequestContext

class TicketTransitionGuard:
    """Enforce valid state transitions for Ticket."""

    VALID_TRANSITIONS = {
        TicketStatus.OPEN: [TicketStatus.ASSIGNED],
        TicketStatus.ASSIGNED: [TicketStatus.RESOLVED],
        TicketStatus.RESOLVED: [TicketStatus.CLOSED],
        TicketStatus.CLOSED: [TicketStatus.OPEN],
    }

    def can_transition(
        self,
        ticket: Ticket,
        to_status: TicketStatus,
        context: RequestContext,
    ) -> tuple[bool, str | None]:
        """Check if transition is allowed. Returns (allowed, error_message)."""

        from_status = ticket.status

        # Check if transition is valid
        if to_status not in self.VALID_TRANSITIONS.get(from_status, []):
            return False, f"Cannot transition from {from_status} to {to_status}"

        # Check guards
        if from_status == TicketStatus.OPEN and to_status == TicketStatus.ASSIGNED:
            if ticket.assigned_to is None:
                return False, "assigned_to is required for this transition"

        if from_status == TicketStatus.ASSIGNED and to_status == TicketStatus.RESOLVED:
            if ticket.resolution is None:
                return False, "resolution is required for this transition"

        if from_status == TicketStatus.CLOSED and to_status == TicketStatus.OPEN:
            if not context.has_role("admin"):
                return False, "Only admin can reopen closed tickets"

        return True, None

    def assert_transition(
        self,
        ticket: Ticket,
        to_status: TicketStatus,
        context: RequestContext,
    ) -> None:
        """Raise exception if transition not allowed."""
        allowed, error = self.can_transition(ticket, to_status, context)
        if not allowed:
            raise TransitionError(error)
```

#### Invariant Validators

From DSL:
```dsl
entity Booking "Booking":
  start_date: datetime required
  end_date: datetime required

  invariant: end_date > start_date
    message: "Check-out must be after check-in"
    code: BOOKING_INVALID_DATES
```

Generated (`backend/validators/booking_invariants.py`):
```python
"""
Invariant validators for Booking entity.
Generated from DSL - DO NOT EDIT.
"""
from datetime import datetime
from ..models.booking import Booking

class BookingInvariantError(Exception):
    """Raised when a Booking invariant is violated."""
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code

class BookingInvariantValidator:
    """Validate Booking invariants."""

    def validate(self, booking: Booking) -> None:
        """Validate all invariants. Raises BookingInvariantError on failure."""
        self.validate_date_order(booking)

    def validate_date_order(self, booking: Booking) -> None:
        """Invariant: end_date > start_date"""
        if not (booking.end_date > booking.start_date):
            raise BookingInvariantError(
                message="Check-out must be after check-in",
                code="BOOKING_INVALID_DATES",
            )

    def is_valid(self, booking: Booking) -> tuple[bool, list[str]]:
        """Check all invariants without raising. Returns (valid, errors)."""
        errors = []
        try:
            self.validate(booking)
        except BookingInvariantError as e:
            errors.append(f"[{e.code}] {e}")
        return len(errors) == 0, errors
```

#### Access Policies

From DSL:
```dsl
entity Document "Document":
  owner: ref User required
  is_public: bool = false

  access:
    read: owner = current_user or is_public = true or role(admin)
    write: owner = current_user or role(admin)
```

Generated (`backend/access/policies.py`):
```python
"""
Access control policies.
Generated from DSL - DO NOT EDIT.
"""
from ..models.document import Document
from .context import RequestContext

class DocumentAccessPolicy:
    """Row-level security for Document entity."""

    def can_read(self, document: Document, context: RequestContext) -> bool:
        """Check if current user can read this document."""
        return (
            document.owner_id == context.user_id
            or document.is_public is True
            or context.has_role("admin")
        )

    def can_write(self, document: Document, context: RequestContext) -> bool:
        """Check if current user can write this document."""
        return (
            document.owner_id == context.user_id
            or context.has_role("admin")
        )

    def filter_readable(
        self,
        query: Select,
        context: RequestContext,
    ) -> Select:
        """Apply read filters to a SQLAlchemy query."""
        if context.has_role("admin"):
            return query  # Admin sees all

        return query.where(
            or_(
                Document.owner_id == context.user_id,
                Document.is_public == True,
            )
        )
```

---

## 8. Frontend Adapters

### 8.1 Adapter Interface

```python
# src/dazzle/eject/adapters/frontend_base.py
class FrontendAdapter(Generator, ABC):
    """Base class for frontend code generators."""

    @abstractmethod
    def generate_types(self) -> GeneratorResult:
        """Generate TypeScript types from entities."""
        pass

    @abstractmethod
    def generate_schemas(self) -> GeneratorResult:
        """Generate Zod schemas for runtime validation."""
        pass

    @abstractmethod
    def generate_client(self) -> GeneratorResult:
        """Generate HTTP client with validation."""
        pass

    @abstractmethod
    def generate_hooks(self) -> GeneratorResult:
        """Generate data fetching hooks."""
        pass
```

### 8.2 React + Zod + TanStack Query Adapter

Generated (`frontend/src/api/types.ts`):
```typescript
/**
 * TypeScript types for API entities.
 * Generated from DSL - DO NOT EDIT.
 */

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_to?: string | null;
  created_at: string;
  updated_at: string;

  // Computed fields (read-only)
  readonly days_open: number;
}

export type TaskStatus = 'todo' | 'in_progress' | 'done';
export type TaskPriority = 'low' | 'medium' | 'high';

export interface TaskCreate {
  title: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  assigned_to?: string | null;
}

export interface TaskUpdate {
  title?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  assigned_to?: string | null;
}
```

Generated (`frontend/src/api/schemas.ts`):
```typescript
/**
 * Zod schemas for runtime validation.
 * Generated from DSL - DO NOT EDIT.
 */
import { z } from 'zod';

export const TaskStatusSchema = z.enum(['todo', 'in_progress', 'done']);
export const TaskPrioritySchema = z.enum(['low', 'medium', 'high']);

export const TaskSchema = z.object({
  id: z.string().uuid(),
  title: z.string().max(200),
  status: TaskStatusSchema,
  priority: TaskPrioritySchema,
  assigned_to: z.string().uuid().nullable().optional(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
  days_open: z.number().int(),  // Computed
});

export const TaskCreateSchema = z.object({
  title: z.string().min(1).max(200),
  status: TaskStatusSchema.optional().default('todo'),
  priority: TaskPrioritySchema.optional().default('medium'),
  assigned_to: z.string().uuid().nullable().optional(),
});

export const TaskUpdateSchema = TaskCreateSchema.partial();

export type Task = z.infer<typeof TaskSchema>;
export type TaskCreate = z.infer<typeof TaskCreateSchema>;
export type TaskUpdate = z.infer<typeof TaskUpdateSchema>;
```

Generated (`frontend/src/api/hooks.ts`):
```typescript
/**
 * TanStack Query hooks for data fetching.
 * Generated from DSL - DO NOT EDIT.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { client } from './client';
import type { Task, TaskCreate, TaskUpdate } from './types';

// Query keys
export const taskKeys = {
  all: ['tasks'] as const,
  lists: () => [...taskKeys.all, 'list'] as const,
  list: (filters: Record<string, unknown>) => [...taskKeys.lists(), filters] as const,
  details: () => [...taskKeys.all, 'detail'] as const,
  detail: (id: string) => [...taskKeys.details(), id] as const,
};

// Queries
export function useTasks(filters?: { status?: string; priority?: string }) {
  return useQuery({
    queryKey: taskKeys.list(filters ?? {}),
    queryFn: () => client.tasks.list(filters),
  });
}

export function useTask(id: string) {
  return useQuery({
    queryKey: taskKeys.detail(id),
    queryFn: () => client.tasks.get(id),
    enabled: !!id,
  });
}

// Mutations
export function useCreateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TaskCreate) => client.tasks.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.lists() });
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) =>
      client.tasks.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: taskKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: taskKeys.lists() });
    },
  });
}

export function useDeleteTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => client.tasks.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.lists() });
    },
  });
}
```

---

## 9. Testing Generation

### 9.1 Contract Tests (Schemathesis)

Generated (`tests/contract/test_openapi.py`):
```python
"""
OpenAPI contract tests using Schemathesis.
Generated from DSL - DO NOT EDIT.

Run with: pytest tests/contract/ -v
"""
import schemathesis

# Load schema from generated OpenAPI spec
schema = schemathesis.from_path("spec/openapi.yaml")

@schema.parametrize()
def test_api_contract(case):
    """
    Automatically test all endpoints against OpenAPI contract.

    This validates:
    - Response status codes match spec
    - Response bodies match declared schemas
    - Required fields are present
    - Field types are correct
    """
    response = case.call_and_validate()
```

### 9.2 State Machine Tests

Generated (`tests/unit/test_ticket_states.py`):
```python
"""
State machine tests for Ticket entity.
Generated from DSL - DO NOT EDIT.
"""
import pytest
from backend.models.ticket import Ticket, TicketStatus
from backend.guards.ticket_transitions import TicketTransitionGuard, TransitionError
from backend.access.context import RequestContext

@pytest.fixture
def guard():
    return TicketTransitionGuard()

@pytest.fixture
def admin_context():
    return RequestContext(user_id="admin-1", roles=["admin"])

@pytest.fixture
def user_context():
    return RequestContext(user_id="user-1", roles=["user"])

class TestTicketTransitions:
    """Test valid and invalid state transitions."""

    def test_open_to_assigned_requires_assignee(self, guard, user_context):
        """Transition open -> assigned requires assigned_to field."""
        ticket = Ticket(status=TicketStatus.OPEN, assigned_to=None)

        allowed, error = guard.can_transition(
            ticket, TicketStatus.ASSIGNED, user_context
        )

        assert not allowed
        assert "assigned_to is required" in error

    def test_open_to_assigned_with_assignee(self, guard, user_context):
        """Transition open -> assigned succeeds with assigned_to."""
        ticket = Ticket(status=TicketStatus.OPEN, assigned_to="user-2")

        allowed, error = guard.can_transition(
            ticket, TicketStatus.ASSIGNED, user_context
        )

        assert allowed
        assert error is None

    def test_closed_to_open_requires_admin(self, guard, user_context):
        """Transition closed -> open requires admin role."""
        ticket = Ticket(status=TicketStatus.CLOSED)

        allowed, error = guard.can_transition(
            ticket, TicketStatus.OPEN, user_context
        )

        assert not allowed
        assert "admin" in error.lower()

    def test_closed_to_open_admin_allowed(self, guard, admin_context):
        """Admin can reopen closed tickets."""
        ticket = Ticket(status=TicketStatus.CLOSED)

        allowed, error = guard.can_transition(
            ticket, TicketStatus.OPEN, admin_context
        )

        assert allowed

    def test_invalid_transition_rejected(self, guard, user_context):
        """Invalid transitions are rejected."""
        ticket = Ticket(status=TicketStatus.OPEN)

        # Cannot skip from open directly to closed
        allowed, error = guard.can_transition(
            ticket, TicketStatus.CLOSED, user_context
        )

        assert not allowed
        assert "Cannot transition" in error
```

### 9.3 Invariant Tests

Generated (`tests/unit/test_booking_invariants.py`):
```python
"""
Invariant tests for Booking entity.
Generated from DSL - DO NOT EDIT.
"""
import pytest
from datetime import datetime, timedelta
from backend.models.booking import Booking
from backend.validators.booking_invariants import (
    BookingInvariantValidator,
    BookingInvariantError,
)

@pytest.fixture
def validator():
    return BookingInvariantValidator()

class TestBookingInvariants:
    """Test entity invariants."""

    def test_end_date_must_be_after_start_date(self, validator):
        """Invariant: end_date > start_date"""
        now = datetime.now()

        # Invalid: end before start
        booking = Booking(
            start_date=now,
            end_date=now - timedelta(days=1),
        )

        with pytest.raises(BookingInvariantError) as exc:
            validator.validate(booking)

        assert exc.value.code == "BOOKING_INVALID_DATES"
        assert "Check-out must be after check-in" in str(exc.value)

    def test_valid_date_range(self, validator):
        """Valid booking passes invariants."""
        now = datetime.now()

        booking = Booking(
            start_date=now,
            end_date=now + timedelta(days=3),
        )

        # Should not raise
        validator.validate(booking)
```

---

## 10. CI Template Generation

### 10.1 GitHub Actions

Generated (`.github/workflows/ci.yml`):
```yaml
# CI workflow for ejected DAZZLE application.
# Generated from DSL - DO NOT EDIT.

name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "20"

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint
        run: |
          ruff check backend/ tests/
          mypy backend/

      - name: Unit tests
        run: pytest tests/unit/ -v --cov=backend

      - name: Contract tests
        run: pytest tests/contract/ -v

  frontend:
    name: Frontend Tests
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Type check
        working-directory: frontend
        run: npm run typecheck

      - name: Lint
        working-directory: frontend
        run: npm run lint

      - name: Test
        working-directory: frontend
        run: npm test

  e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    needs: [backend, frontend]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}

      - name: Install Playwright
        run: npx playwright install --with-deps

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          cd frontend && npm ci

      - name: Run E2E tests
        run: pytest tests/e2e/ -v
```

---

## 11. DNR Component Reuse (Optional)

Ejected code can optionally import DNR components for consistency:

### 11.1 Reuse Mode Configuration

```toml
[ejection]
reuse_dnr = true  # Import DNR components where possible
```

### 11.2 Example: Reusing DNR Migrations

```python
# backend/db/migrations.py (when reuse_dnr = true)
"""
Database migrations using DNR migration system.
"""
from dazzle_dnr_back.runtime.migrations import (
    MigrationManager,
    generate_migrations_from_spec,
)

# Reuse DNR's migration infrastructure
manager = MigrationManager(database_url="sqlite:///./app.db")
```

### 11.3 Example: Reusing DNR Auth

```python
# backend/auth/session.py (when reuse_dnr = true)
"""
Session authentication using DNR auth system.
"""
from dazzle_dnr_back.runtime.auth import (
    SessionAuth,
    hash_password,
    verify_password,
)

# Reuse DNR's authentication
auth = SessionAuth(secret_key=settings.SECRET_KEY)
```

---

## 12. Implementation Plan

### Phase 1: Foundation (Week 1-2)
- [ ] `EjectionConfig` parser (extend dazzle.toml)
- [ ] CLI commands (`dazzle eject`, `dazzle eject config`)
- [ ] Adapter registry and base classes
- [ ] Unit tests for config parsing

### Phase 2: FastAPI Backend Adapter (Week 3-4)
- [ ] Models generator (from entities)
- [ ] Schemas generator (Pydantic)
- [ ] Routers generator (CRUD endpoints)
- [ ] Guards generator (from state machines)
- [ ] Validators generator (from invariants)
- [ ] Access generator (from access rules)
- [ ] Integration tests

### Phase 3: React Frontend Adapter (Week 5-6)
- [ ] Types generator (TypeScript)
- [ ] Schemas generator (Zod)
- [ ] Client generator (fetch wrapper)
- [ ] Hooks generator (TanStack Query)
- [ ] Unit tests

### Phase 4: Testing & CI Adapters (Week 7)
- [ ] Schemathesis contract tests
- [ ] Unit test stubs per entity
- [ ] State machine tests
- [ ] Invariant tests
- [ ] GitHub Actions workflow

### Phase 5: Polish & Documentation (Week 8)
- [ ] OpenAPI parallel generation
- [ ] README generation
- [ ] Docker/docker-compose
- [ ] End-to-end validation
- [ ] Documentation

---

## 13. Success Criteria

1. **Functional Ejection**
   - `dazzle eject` produces runnable FastAPI + React application
   - Backend starts with `uvicorn backend.app:app`
   - Frontend builds with `npm run build`

2. **Business Logic Preserved**
   - State machine guards enforce transitions
   - Invariant validators prevent invalid data
   - Access policies filter queries

3. **Test Coverage**
   - Contract tests validate API spec
   - State machine tests cover all transitions
   - Invariant tests cover all rules

4. **CI Ready**
   - Generated workflow runs on GitHub Actions
   - All tests pass on fresh clone

5. **Backward Compatible**
   - Existing `dazzle.toml` files work unchanged
   - DNR remains default runtime
   - Ejection is opt-in

---

## 14. Future Adapters (Post v0.7.2)

| Adapter | Target Version | Notes |
|---------|---------------|-------|
| Django Backend | v0.8.x | Django ORM, DRF or Ninja |
| Vue Frontend | v0.8.x | Vue 3 + Composition API |
| Next.js Frontend | v0.9.x | App Router, Server Components |
| Flask Backend | v0.9.x | Minimal API |
| GitLab CI | v0.8.x | `.gitlab-ci.yml` |

---

## Appendix A: Comparison with Original Spec

| Aspect | Original Spec | Revised Spec |
|--------|---------------|--------------|
| Config file | `dazzle.toolchain.yaml` | `dazzle.toml` [ejection] section |
| Intermediate format | OpenAPI 3.1 | AppSpec (direct) |
| Business logic | "No business logic" | Full logic from DSL |
| Positioning | Alternative to DNR | Escape hatch from DNR |
| DNR relationship | Independent | Can reuse DNR components |
| Base classes | New | Extends existing Generator |

---

## Appendix B: Migration from DNR to Ejected

```bash
# 1. Enable ejection in config
echo '[ejection]
enabled = true' >> dazzle.toml

# 2. Generate ejected code
dazzle eject

# 3. Review generated code
ls generated/

# 4. Install dependencies
cd generated
pip install -r requirements.txt
cd frontend && npm install

# 5. Run ejected application
uvicorn backend.app:app --reload

# 6. (Optional) Remove DNR dependency
# Edit pyproject.toml to remove dazzle dependencies
```

---

**Document Owner**: Claude + James
**Last Review**: 2025-12-10
**Status**: Ready for Implementation
