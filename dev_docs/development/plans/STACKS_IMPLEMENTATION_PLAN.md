# DAZZLE Stacks Implementation - Stage Plan

## Current State Analysis

**Already Implemented:**
- ✅ Backend plugin system with registry
- ✅ OpenAPI backend (generates API specs)
- ✅ Docker infra backend (generates compose.yaml, Dockerfile)
- ✅ Terraform infra backend (generates cloud infrastructure)
- ✅ Manifest system (dazzle.toml parsing)
- ✅ CLI infrastructure (build, init, infra commands)
- ✅ IR system (AppSpec is infra-agnostic)

**Gaps Identified:**
- ❌ No stack abstraction layer
- ❌ No Django backend
- ❌ No Next.js frontend backend
- ❌ Build command doesn't support multiple backends
- ❌ No demo command
- ❌ No stack presets

---

## Stage 1: Stack System Foundation
**Duration:** Low complexity
**Dependencies:** None

**Tasks:**

1. **Extend ProjectManifest** for stacks (`core/manifest.py`):
   ```python
   @dataclass
   class StackConfig:
       name: str
       backends: List[str]
       description: Optional[str] = None

   @dataclass
   class ProjectManifest:
       # ... existing fields
       stack: Optional[StackConfig] = None
   ```
   - Parse `[stack]` section from dazzle.toml
   - Validate backend names exist

2. **Create Stack Registry** (`core/stacks.py`):
   ```python
   @dataclass
   class StackPreset:
       name: str
       description: str
       backends: List[str]
       example_dsl: Optional[str] = None  # For demo command

   BUILTIN_STACKS = {
       "django_next": StackPreset(...),
       "django_next_demo": StackPreset(...),
   }
   ```
   - Registry of built-in stack presets
   - Function to resolve stack name → backend list

3. **Stack Validation**:
   - Ensure all backends in stack exist
   - Detect circular dependencies (future-proofing)
   - Validate backend execution order

**Deliverables:**
- `src/dazzle/core/manifest.py` (extended)
- `src/dazzle/core/stacks.py` (new)
- Unit tests for stack parsing

---

## Stage 2: Django API Backend
**Duration:** High complexity
**Dependencies:** Stage 1

**Tasks:**

1. **Create Django Backend** (`backends/django_api.py`):
   - Class: `DjangoAPIBackend(Backend)`
   - Capabilities:
     ```python
     supports_incremental=False
     output_formats=["django"]
     ```

2. **Django Project Generation**:
   - `_generate_project_structure()` - Create Django project skeleton
   - `_generate_models()` - Entity → Django models
   - `_generate_serializers()` - DRF serializers for entities
   - `_generate_viewsets()` - DRF viewsets with CRUD
   - `_generate_urls()` - URL routing
   - `_generate_settings()` - settings.py with DRF config
   - `_generate_requirements()` - requirements.txt with Django, DRF, etc.
   - `_generate_openapi_spec()` - Export OpenAPI from DRF schema

3. **Entity Mapping Logic**:
   - FieldType → Django field types (CharField, IntegerField, etc.)
   - Field modifiers → Django field options (null, blank, unique, etc.)
   - Relationships → ForeignKey, ManyToMany
   - Enums → Django choices or separate model

4. **Surface Mapping Logic**:
   - Surfaces → ViewSets with appropriate actions
   - mode: list → list action
   - mode: view → retrieve action
   - mode: create → create action
   - mode: edit → update/partial_update actions

**Output Structure:**
```
backend/
├── manage.py
├── requirements.txt
├── app_name/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
└── api/
    ├── __init__.py
    ├── models.py
    ├── serializers.py
    ├── views.py
    ├── urls.py
    └── migrations/
        └── __init__.py
```

**Deliverables:**
- `src/dazzle/backends/django_api.py`
- Django templates in `src/dazzle/templates/django/`
- Integration tests

---

## Stage 3: Next.js Frontend Backend
**Duration:** High complexity
**Dependencies:** Stage 2 (for OpenAPI consumption)

**Tasks:**

1. **Create Next.js Backend** (`backends/nextjs_frontend.py`):
   - Class: `NextJSFrontendBackend(Backend)`
   - Capabilities:
     ```python
     supports_incremental=False
     output_formats=["nextjs"]
     requires_config=False
     ```

2. **Next.js Project Generation**:
   - `_generate_project_structure()` - Next.js 13+ app directory
   - `_generate_api_client()` - TypeScript API client from OpenAPI
   - `_generate_pages()` - Surface → Next.js pages/routes
   - `_generate_components()` - Reusable UI components
   - `_generate_package_json()` - Dependencies (React, Next.js, etc.)
   - `_generate_tsconfig()` - TypeScript configuration
   - `_generate_env_example()` - Environment variables

3. **Surface → Page Mapping**:
   - mode: list → Table/Grid view page
   - mode: view → Detail view page
   - mode: create → Form page
   - mode: edit → Edit form page
   - Use Shadcn/ui or similar for components

4. **API Client Generation**:
   - Consume OpenAPI spec (if available)
   - Generate typed API functions
   - Handle authentication/authorization
   - Error handling wrapper

5. **Experience → Flow Mapping**:
   - Multi-step experiences → Wizard/Stepper components
   - Navigation between surfaces
   - State management (React Context or Zustand)

**Output Structure:**
```
frontend/
├── package.json
├── tsconfig.json
├── next.config.js
├── .env.example
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── [entity]/
│   │   ├── page.tsx        # List view
│   │   ├── [id]/
│   │   │   ├── page.tsx    # Detail view
│   │   │   └── edit/
│   │   │       └── page.tsx # Edit view
│   │   └── new/
│   │       └── page.tsx     # Create view
│   └── components/
│       ├── forms/
│       ├── tables/
│       └── layouts/
└── lib/
    ├── api/
    │   └── client.ts
    └── types/
        └── generated.ts
```

**Deliverables:**
- `src/dazzle/backends/nextjs_frontend.py`
- Next.js templates in `src/dazzle/templates/nextjs/`
- Integration tests

---

## Stage 4: Multi-Backend Build System
**Duration:** Medium complexity
**Dependencies:** Stages 1-3

**Tasks:**

1. **Enhance Build Command** (`cli.py`):
   - Add `--stack <name>` option
   - Add `--backends <comma-separated>` option
   - Support building multiple backends sequentially
   - Share artifacts between backends (e.g., OpenAPI spec)

2. **Backend Orchestration**:
   ```python
   def build_stack(
       appspec: AppSpec,
       backends: List[str],
       output_dir: Path,
       manifest: ProjectManifest,
   ) -> None:
       """Build multiple backends in order."""
       artifacts = {}  # Shared artifacts between backends

       for backend_name in backends:
           backend = get_backend(backend_name)
           backend_dir = output_dir / backend_name

           # Pass shared artifacts (e.g., OpenAPI spec)
           backend.generate(
               appspec,
               backend_dir,
               artifacts=artifacts,
           )

           # Collect artifacts for next backend
           artifacts[backend_name] = backend.get_artifacts(backend_dir)
   ```

3. **Artifact Sharing**:
   - OpenAPI backend produces spec → consumed by nextjs_frontend
   - Django backend produces OpenAPI → consumed by nextjs_frontend
   - infra_docker needs to know all services to generate compose.yaml

4. **Build Command Examples**:
   ```bash
   dazzle build                              # Use stack from manifest
   dazzle build --stack django_next          # Use specific stack
   dazzle build --backends django_api,nextjs # Build specific backends
   dazzle build --backend openapi            # Single backend (existing)
   ```

**Deliverables:**
- Enhanced `src/dazzle/cli.py` build command
- Backend orchestration logic
- Artifact sharing system

---

## Stage 5: Demo Command
**Duration:** Medium complexity
**Dependencies:** Stage 4

**Tasks:**

1. **Create Demo Command** (`cli.py`):
   ```bash
   dazzle demo django_next        # Create demo with stack
   dazzle demo --list             # List available demos
   ```

2. **Demo Generation Flow**:
   - Create project directory
   - Write example dazzle.toml with stack
   - Write example DSL (use support_tickets or simple_task)
   - Run `dazzle build` automatically
   - Generate README with run instructions
   - Print next steps to console

3. **Demo Templates**:
   - Support tickets example (complex)
   - Simple task example (minimal)
   - Blog example (new, medium complexity)

4. **Post-Generation Instructions**:
   ```
   ✓ Demo created: ./my-demo

   Next steps:
     cd my-demo
     docker compose up -d

   Services:
     - Frontend: http://localhost:3000
     - Backend API: http://localhost:8000
     - API Docs: http://localhost:8000/api/docs
   ```

**Deliverables:**
- `demo` command in CLI
- Demo templates
- Generated README with instructions

---

## Stage 6: Stack Presets & Documentation
**Duration:** Low complexity
**Dependencies:** Stage 5

**Tasks:**

1. **Define Built-in Stacks** (`core/stacks.py`):
   ```python
   BUILTIN_STACKS = {
       "django_next": StackPreset(
           name="django_next",
           description="Django REST + Next.js frontend + Docker",
           backends=["django_api", "nextjs_frontend", "infra_docker"],
       ),
       "django_next_cloud": StackPreset(
           name="django_next_cloud",
           description="Django + Next.js + Docker + Terraform",
           backends=["django_api", "nextjs_frontend", "infra_docker", "infra_terraform"],
       ),
       "api_only": StackPreset(
           name="api_only",
           description="Django API + OpenAPI spec",
           backends=["django_api", "openapi"],
       ),
   }
   ```

2. **Enhance Init Command**:
   ```bash
   dazzle init --stack django_next ./my-project
   ```
   - Write dazzle.toml with stack configuration
   - Generate blank DSL or copy from template
   - Optionally run build

3. **Documentation**:
   - Update README.md with stack examples
   - Create `docs/STACKS.md` guide
   - Document each built-in stack
   - Show how to define custom stacks

4. **Stack Introspection**:
   ```bash
   dazzle stacks list              # List available stacks
   dazzle stacks show django_next  # Show stack details
   ```

**Deliverables:**
- Stack presets in `core/stacks.py`
- Enhanced init command
- Documentation (`docs/STACKS.md`)
- Stack list/show commands

---

## Stage 7: Integration & Polish
**Duration:** Medium complexity
**Dependencies:** Stages 1-6

**Tasks:**

1. **Update Docker Backend** for multi-service:
   - Detect when multiple backends are used (Django + Next.js)
   - Generate compose.yaml with all services:
     ```yaml
     services:
       backend:
         build: ./backend
         ports: ["8000:8000"]
       frontend:
         build: ./frontend
         ports: ["3000:3000"]
       db:
         image: postgres:15
       redis:
         image: redis:7
     ```

2. **Cross-Backend Testing**:
   - Test django_api + nextjs_frontend integration
   - Test django_api + infra_docker
   - Test full stack (all 3 backends)
   - Verify API client generation
   - Verify OpenAPI spec consumption

3. **Error Handling**:
   - Better error messages for missing backends
   - Validation for backend compatibility
   - Warnings for missing dependencies

4. **Examples Update**:
   - Add [stack] section to examples/support_tickets/dazzle.toml
   - Add [stack] section to examples/simple_task/dazzle.toml
   - Provide runnable demos

**Deliverables:**
- Enhanced Docker backend for multi-service
- Integration tests
- Updated examples with stacks

---

## Implementation Summary

### Complexity Breakdown
| Stage | Complexity | Estimated LOC | Critical? |
|-------|-----------|---------------|-----------|
| 1. Stack Foundation | Low | ~150 | Yes |
| 2. Django Backend | High | ~800 | Yes |
| 3. Next.js Backend | High | ~700 | Yes |
| 4. Multi-Backend Build | Medium | ~300 | Yes |
| 5. Demo Command | Medium | ~200 | Yes |
| 6. Stack Presets | Low | ~100 | Yes |
| 7. Integration & Polish | Medium | ~300 | Yes |
| **Total** | | **~2,550** | |

### Recommended Order
1. **Stage 1** - Foundation (stack system, manifest)
2. **Stage 2** - Django backend (most complex, foundational)
3. **Stage 4** - Multi-backend build (enables composition)
4. **Stage 3** - Next.js backend (depends on Django for OpenAPI)
5. **Stage 5** - Demo command (user-facing feature)
6. **Stage 6** - Stack presets & docs
7. **Stage 7** - Integration & polish

### Key Design Decisions

1. **Backends Remain Independent**: Each backend can run standalone or as part of a stack
2. **Artifact Sharing**: Lightweight mechanism for passing OpenAPI specs between backends
3. **Stack = List of Backends**: Simple, no complex dependency resolution
4. **Demo Command**: Opinionated, batteries-included experience
5. **No DSL Changes**: All abstraction at manifest/CLI level

### Dependencies on Existing Work

**Builds On:**
- Backend plugin system ✅
- Manifest parsing ✅
- CLI infrastructure ✅
- OpenAPI backend ✅
- Docker/Terraform infra backends ✅

**Doesn't Break:**
- Existing single-backend workflows
- Current examples
- OpenAPI generation
- Infrastructure generation

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Django backend complexity | Start with minimal viable Django project, iterate |
| Next.js rapidly evolving | Target Next.js 14+ app router, document version |
| Backend coordination | Keep artifact sharing minimal, use file-based exchange |
| Demo fragility | Pin dependency versions, provide docker-based demos |

---

## Example: django_next Stack Usage

**dazzle.toml:**
```toml
[project]
name = "my_app"
version = "0.1.0"
root = "myapp.core"

[stack]
name = "django_next"

[modules]
paths = ["./dsl"]
```

**Generated Structure:**
```
my_app/
├── dazzle.toml
├── dsl/
│   └── app.dsl
├── backend/              # From django_api
│   ├── manage.py
│   ├── api/
│   └── requirements.txt
├── frontend/             # From nextjs_frontend
│   ├── package.json
│   ├── app/
│   └── lib/
└── infra/                # From infra_docker
    └── docker/
        ├── Dockerfile.backend
        ├── Dockerfile.frontend
        └── compose.yaml
```

**Commands:**
```bash
# Create demo
dazzle demo django_next ./my-app

# Or build manually
dazzle init --stack django_next ./my-app
cd my-app
# ... write DSL ...
dazzle build

# Run
docker compose up
```

---

## Implementation Status

- [ ] Stage 1: Stack System Foundation
- [ ] Stage 2: Django API Backend
- [ ] Stage 3: Next.js Frontend Backend
- [ ] Stage 4: Multi-Backend Build System
- [ ] Stage 5: Demo Command
- [ ] Stage 6: Stack Presets & Documentation
- [ ] Stage 7: Integration & Polish
