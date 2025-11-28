# DNR Architecture Principles

**Date**: 2025-11-27
**Status**: Canonical architectural decisions

---

## Core Principles

### 1. Spec-First, Framework-Agnostic

**BackendSpec** and **UISpec** are the source of truth.
- Language-agnostic specifications
- Multiple runtimes/builders can consume them
- No framework lock-in

### 2. Backend Architecture

#### 2.1 Layers

```
BackendSpec (language-agnostic truth)
    ↓
DazzleModel (thin Python abstraction)
    ↓
Adapters/Builders (framework-specific)
    ├── Pydantic + FastAPI
    ├── Django + DRF (future)
    ├── Dataclasses + manual wiring (future)
    └── Rust structs, TS types (future)
```

#### 2.2 Key Decisions

**❌ NOT this**:
- Pydantic as the core abstraction
- Framework-specific types in specs

**✅ DO this**:
- BackendSpec stores pure data (entities, fields, services)
- DazzleModel: thin Python wrapper that knows how to:
  - Store field metadata
  - Validate instances (own logic or delegated)
  - Generate framework-specific code when requested
- Pydantic is just one builder plugin (for FastAPI/OpenAPI use case)

#### 2.3 Implementation Strategy

**Current (v0.1)**: BackendSpec uses Pydantic for validation
- This is OK for bootstrapping
- Specs themselves are still framework-agnostic data

**Future (v0.2+)**: Add DazzleModel abstraction layer
- BackendSpec → DazzleModel (pure Python)
- DazzleModel → Pydantic (adapter for FastAPI)
- DazzleModel → Dataclasses (adapter for lean runtime)
- Keep Pydantic specs for JSON schema generation

### 3. UI Architecture

#### 3.1 Pure Native JavaScript

**Why pure JS**:
- ✅ Maximum control
- ✅ Minimum footprint
- ✅ Easy to host anywhere
- ✅ Fully aligned with LLM-first architecture
- ✅ Easier to reason about mobile runtime mapping

**❌ NOT using**:
- React (too heavy, unnecessary abstraction)
- Vue, Svelte, etc.
- Build tools as core dependency (Vite optional for dev)

**✅ Using**:
- Pure DOM manipulation
- Native Web Components
- Native JavaScript modules (ESM)
- CSS variables for theming
- LocalStorage/SessionStorage for state

#### 3.2 UI Runtime Components

```
UISpec (declarative spec)
    ↓
DNR-UI Runtime (pure JS)
    ├── Renderer: ViewNode → DOM
    ├── State Manager: Native signals pattern
    ├── Action Executor: Event → State updates
    └── Theme Engine: CSS variables
```

#### 3.3 State Management

**Lightweight signals pattern**:
- Pure JavaScript implementation
- No external dependencies
- Observable state with subscriptions
- Scoped state (local, workspace, app, session)

#### 3.4 Component System

**Native Web Components**:
- CustomElements API
- Shadow DOM for encapsulation
- No framework overhead
- Easy to distribute and embed

### 4. Spec Design Principles

#### 4.1 BackendSpec

**Current implementation** (src/dazzle_dnr_back/specs/):
- Uses Pydantic for validation (bootstrap convenience)
- Frozen models (immutable)
- All types are data-oriented (no behavior)

**Schema**:
```python
EntitySpec:
    name: str
    fields: list[FieldSpec]
    relations: list[RelationSpec]
    # Pure data, no methods except query helpers
```

#### 4.2 UISpec

**Current implementation** (src/dazzle_dnr_ui/specs/):
- Uses Pydantic for validation
- Pure data structures
- View trees are declarative (not imperative)

**Schema**:
```python
ComponentSpec:
    name: str
    props_schema: PropsSchema
    view: ViewNode  # Declarative tree
    state: list[StateSpec]
    actions: list[ActionSpec]
```

### 5. MCP Integration

**Design**:
- MCP tools manipulate specs (BackendSpec, UISpec)
- LLMs work with high-level semantic operations
- Runtime consumes specs, never directly edited

**Tools**:
- `create_backend_service` → modifies BackendSpec
- `patch_uispec_component` → modifies UISpec
- Specs are serialized to JSON for storage

### 6. Build Process

```
DSL → AppSpec (existing Dazzle pipeline)
    ↓
AppSpec → BackendSpec (converter)
    ↓
BackendSpec → Runtime Artifacts
    ├── FastAPI app (Pydantic adapter)
    ├── OpenAPI spec
    └── SQLAlchemy models (optional)

AppSpec → UISpec (converter)
    ↓
UISpec → Runtime Artifacts
    ├── Pure JS modules
    ├── Web Components
    └── Static HTML/CSS
```

### 7. Deployment

**Backend**:
- FastAPI: Uvicorn/Gunicorn + ASGI
- Django: wsgi.py (future)
- Standalone: Pure Python + dataclasses (future)

**Frontend**:
- Static files: Host anywhere (S3, Netlify, Vercel)
- No build step required (ESM modules)
- Optional: Bundle with esbuild for optimization

### 8. Migration Path from Current Code

**Phase 1 (Current - v0.1)**:
- Specs use Pydantic (pragmatic)
- Focus on completeness and correctness

**Phase 2 (v0.2)**:
- Introduce DazzleModel abstraction
- Refactor FastAPI builder to use DazzleModel
- Keep Pydantic specs for JSON schema

**Phase 3 (v0.3+)**:
- Add alternative builders (Django, dataclasses)
- Pure Python kernel, multiple adapters

---

## Decision Log

### 2025-11-27: Framework Independence

**Decision**: Specs are language-agnostic, Pydantic is an adapter

**Rationale**:
- BackendSpec should be consumable by any language/framework
- Pydantic is excellent for Python validation and OpenAPI
- But it shouldn't be the core abstraction
- Future: Generate Rust, TS, Go from same BackendSpec

**Impact**:
- Specs remain Pydantic-based for now (bootstrap)
- Document that Pydantic is implementation detail
- Design for easy extraction later

### 2025-11-27: Pure Native JS for UI

**Decision**: DNR-UI uses pure JavaScript, no frameworks

**Rationale**:
- Minimal footprint
- Maximum control
- Easy to understand and reason about
- Aligns with LLM-first architecture
- Mobile runtime mapping is simpler

**Impact**:
- No React, Vue, Svelte dependencies
- Custom state management (signals pattern)
- Native Web Components
- Smaller bundle, faster load

---

## References

- DNR-Spec-v1.md: Original specification
- DNR-Components-v1.md: Component registry
- DNR-MCP-Spec-v1.md: MCP interface
- DNR-Implementation-Plan-v1.md: Implementation roadmap
