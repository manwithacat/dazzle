# DNR Implementation Plan v1

**Created**: 2025-11-27
**Status**: Draft
**Approach**: Specs-first, monorepo with separate packages, MCP from start

---

## 1. Executive Summary

This plan implements the Dazzle Native Runtime (DNR) as defined in DNR-Spec-v1, DNR-Components-v1, and DNR-MCP-Spec-v1.

**Key Decisions**:
- **Architecture**: Monorepo with separate packages (dazzle-dnr-back, dazzle-dnr-ui)
- **Development Strategy**: Define all spec types first, then build runtimes
- **MCP Integration**: Build MCP interface from the start for LLM-driven development
- **Compatibility**: Parallel evolution with existing Dazzle stacks

**Timeline Overview**:
- Stage 1: BackendSpec & UISpec type definitions (1-2 weeks)
- Stage 2: MCP interface skeleton (1 week)
- Stage 3: DNR-Back runtime implementation (2-3 weeks)
- Stage 4: DNR-UI runtime implementation (3-4 weeks)
- Stage 5: Integration & examples (1-2 weeks)

---

## 2. Repository Structure

```
Dazzle/
├── src/
│   ├── dazzle/                     # Existing core package
│   │   ├── core/                   # DSL, IR, linker, etc.
│   │   ├── stacks/                 # Existing stacks
│   │   ├── llm/                    # LLM integration
│   │   ├── mcp/                    # MCP server (will extend)
│   │   └── ...
│   │
│   ├── dazzle_dnr_back/            # NEW: Backend runtime package
│   │   ├── __init__.py
│   │   ├── specs/                  # BackendSpec types
│   │   │   ├── __init__.py
│   │   │   ├── entity.py           # EntitySpec, FieldSpec, RelationSpec
│   │   │   ├── service.py          # ServiceSpec
│   │   │   ├── endpoint.py         # EndpointSpec
│   │   │   ├── auth.py             # AuthRuleSpec, TenancyRuleSpec
│   │   │   └── backend_spec.py     # BackendSpec aggregate
│   │   ├── runtime/                # DNR-Back runtime
│   │   │   ├── __init__.py
│   │   │   ├── models.py           # Pydantic model generation
│   │   │   ├── services.py         # Service stub generation
│   │   │   ├── routes.py           # FastAPI route generation
│   │   │   ├── persistence.py      # SQLAlchemy integration
│   │   │   ├── openapi.py          # OpenAPI generation
│   │   │   └── server.py           # Runtime server
│   │   ├── converters/             # AppSpec → BackendSpec
│   │   │   ├── __init__.py
│   │   │   ├── entity_converter.py
│   │   │   └── surface_converter.py
│   │   └── tests/
│   │
│   └── dazzle_dnr_ui/              # NEW: UI runtime package
│       ├── __init__.py
│       ├── specs/                  # UISpec types
│       │   ├── __init__.py
│       │   ├── workspace.py        # WorkspaceSpec
│       │   ├── component.py        # ComponentSpec
│       │   ├── view.py             # ViewNode types
│       │   ├── state.py            # StateSpec
│       │   ├── actions.py          # ActionSpec, EffectSpec
│       │   ├── theme.py            # ThemeSpec, VariantSpec
│       │   └── ui_spec.py          # UISpec aggregate
│       ├── runtime/                # DNR-UI runtime
│       │   ├── __init__.py
│       │   ├── renderer.py         # DOM rendering engine
│       │   ├── state_manager.py    # Signals-based state system
│       │   ├── action_executor.py  # Action and effect execution
│       │   ├── theme_engine.py     # Theme token application
│       │   └── server.py           # Development server
│       ├── components/             # Built-in component registry
│       │   ├── __init__.py
│       │   ├── primitives/         # Primitive components
│       │   │   ├── __init__.py
│       │   │   ├── page.py
│       │   │   ├── card.py
│       │   │   ├── data_table.py
│       │   │   ├── form.py
│       │   │   └── ...
│       │   └── patterns/           # Pattern components
│       │       ├── __init__.py
│       │       ├── filterable_table.py
│       │       ├── crud_page.py
│       │       └── ...
│       ├── converters/             # AppSpec → UISpec
│       │   ├── __init__.py
│       │   ├── workspace_converter.py
│       │   └── surface_converter.py
│       └── tests/
│
├── examples/
│   └── dnr_examples/               # NEW: DNR example projects
│       ├── simple_task_dnr/
│       └── support_tickets_dnr/
│
└── dev_docs/
    └── Dazzle_Native_Runtime/      # Specs and planning docs
        ├── DNR-Spec-v1.md
        ├── DNR-Components-v1.md
        ├── DNR-MCP-Spec-v1.md
        └── DNR-Implementation-Plan-v1.md (this file)
```

---

## 3. Stage 1: BackendSpec Type Definitions

**Goal**: Define complete type system for BackendSpec using Pydantic

**Duration**: 1-2 weeks

### 3.1 Tasks

#### 3.1.1 Package Setup
- [ ] Create `src/dazzle_dnr_back/` package structure
- [ ] Set up pyproject.toml for `dazzle-dnr-back` package
- [ ] Configure as editable install in monorepo
- [ ] Add to CI/CD pipeline

#### 3.1.2 Core Spec Types
Implement Pydantic models for BackendSpec (based on DNR-Spec-v1 section 3.2):

**File: `src/dazzle_dnr_back/specs/entity.py`**
- [ ] `EntitySpec` - entity definition with fields, relations, metadata
- [ ] `FieldSpec` - field with type, validators, constraints
- [ ] `RelationSpec` - relationships between entities
- [ ] `ValidatorSpec` - validation rules
- [ ] Type definitions: `ScalarType`, `EnumType`, `RefType`

**File: `src/dazzle_dnr_back/specs/service.py`**
- [ ] `ServiceSpec` - domain operations
- [ ] `SchemaSpec` - input/output schemas
- [ ] `DomainOperation` - operation types (CRUD, custom)
- [ ] `EffectSpec` - side effects
- [ ] `BusinessRuleSpec` - constraints and rules

**File: `src/dazzle_dnr_back/specs/endpoint.py`**
- [ ] `EndpointSpec` - HTTP/RPC mapping
- [ ] HTTP method enumeration
- [ ] Path template handling
- [ ] `RateLimitSpec` - rate limiting configuration

**File: `src/dazzle_dnr_back/specs/auth.py`**
- [ ] `AuthRuleSpec` - authentication rules
- [ ] `TenancyRuleSpec` - multi-tenancy rules
- [ ] Permission models
- [ ] Role-based access control types

**File: `src/dazzle_dnr_back/specs/backend_spec.py`**
- [ ] `BackendSpec` - aggregate root
- [ ] Validation methods
- [ ] Helper methods for querying entities, services, endpoints

#### 3.1.3 UISpec Type Definitions
Implement Pydantic models for UISpec (based on DNR-Spec-v1 section 4.2):

**File: `src/dazzle_dnr_ui/specs/workspace.py`**
- [ ] `WorkspaceSpec` - semantic page/layout specification
- [ ] `LayoutSpec` - layout variants (singleColumn, twoColumnWithHeader, appShell)
- [ ] `RouteSpec` - routing configuration

**File: `src/dazzle_dnr_ui/specs/component.py`**
- [ ] `ComponentSpec` - component definition
- [ ] `PropsSchema` - component props specification
- [ ] Component metadata types

**File: `src/dazzle_dnr_ui/specs/view.py`**
- [ ] `ViewNode` - view tree node (union type)
- [ ] `ElementNode` - DOM element representation
- [ ] `ConditionalNode` - conditional rendering
- [ ] `LoopNode` - list rendering
- [ ] `SlotNode` - content slots

**File: `src/dazzle_dnr_ui/specs/state.py`**
- [ ] `StateSpec` - state declaration
- [ ] `StateScope` - scope enumeration (local, workspace, app, session)
- [ ] `Binding` - data binding types (literal, prop, state, derived)

**File: `src/dazzle_dnr_ui/specs/actions.py`**
- [ ] `ActionSpec` - action definition
- [ ] `EffectSpec` - effect types (fetch, navigate, log, toast)
- [ ] `TransitionSpec` - state transitions
- [ ] `PatchSpec` - state update patches

**File: `src/dazzle_dnr_ui/specs/theme.py`**
- [ ] `ThemeSpec` - theme tokens
- [ ] `VariantSpec` - theme variants
- [ ] `TextStyle` - typography definitions
- [ ] Token types for colors, spacing, radii

**File: `src/dazzle_dnr_ui/specs/ui_spec.py`**
- [ ] `UISpec` - aggregate root
- [ ] Component registry
- [ ] Workspace registry
- [ ] Theme registry

#### 3.1.4 Testing
- [ ] Unit tests for all spec types
- [ ] Validation tests (Pydantic validators)
- [ ] Serialization tests (to/from JSON)
- [ ] Example spec fixtures

### 3.2 Deliverables
- ✅ Complete BackendSpec type system with Pydantic models
- ✅ Complete UISpec type system with Pydantic models
- ✅ JSON schema generation from Pydantic models
- ✅ Comprehensive test coverage (>90%)
- ✅ API documentation (docstrings + examples)

---

## 4. Stage 2: MCP Interface Skeleton

**Goal**: Implement MCP tools for spec manipulation (based on DNR-MCP-Spec-v1)

**Duration**: 1 week

### 4.1 Tasks

#### 4.1.1 Extend Existing MCP Server
Enhance `src/dazzle/mcp/server.py` with DNR-specific tools:

**Backend Tools**:
- [ ] `list_backend_services` - list available services
- [ ] `get_backend_service_spec` - fetch full ServiceSpec
- [ ] `create_backend_service` - create new service
- [ ] `patch_backend_service` - modify existing service
- [ ] `list_backend_entities` - list entities in BackendSpec

**UI Tools**:
- [ ] `list_dnr_components` - list UI components (primitives/patterns)
- [ ] `get_dnr_component_spec` - fetch full ComponentSpec
- [ ] `list_workspace_layouts` - list available layouts
- [ ] `create_uispec_component` - create new component
- [ ] `patch_uispec_component` - modify component
- [ ] `compose_workspace` - create/update workspace

#### 4.1.2 Component Registry Tools
**File: `src/dazzle_dnr_ui/components/registry.py`**
- [ ] `ComponentRegistry` class
- [ ] Registration mechanism for primitives and patterns
- [ ] Query methods (by name, category, tags)
- [ ] Metadata extraction for MCP

#### 4.1.3 MCP Integration
- [ ] Update `src/dazzle/mcp/tools.py` with DNR tools
- [ ] Add JSON schema generation for tool parameters
- [ ] Implement tool handlers
- [ ] Add error handling and validation

#### 4.1.4 Testing
- [ ] Unit tests for each MCP tool
- [ ] Integration tests with MCP protocol
- [ ] LLM interaction tests (mock LLM calls)

### 4.2 Deliverables
- ✅ MCP server with DNR tools implemented
- ✅ Component registry with query capabilities
- ✅ MCP protocol compliance
- ✅ Test coverage for all tools

---

## 5. Stage 3: AppSpec → BackendSpec/UISpec Converters

**Goal**: Convert existing Dazzle AppSpec to new BackendSpec and UISpec

**Duration**: 1 week

### 5.1 Tasks

#### 5.1.1 Backend Converter
**File: `src/dazzle_dnr_back/converters/entity_converter.py`**
- [ ] Convert `ir.Entity` → `BackendSpec.EntitySpec`
- [ ] Map field types from AppSpec to BackendSpec
- [ ] Extract validators and constraints
- [ ] Handle relationships and foreign keys

**File: `src/dazzle_dnr_back/converters/surface_converter.py`**
- [ ] Infer `ServiceSpec` from `ir.Surface` CRUD patterns
- [ ] Generate `EndpointSpec` for surface actions
- [ ] Map auth and tenancy rules
- [ ] Handle custom actions

**File: `src/dazzle_dnr_back/converters/__init__.py`**
- [ ] `convert_appspec_to_backend(appspec: ir.AppSpec) -> BackendSpec`
- [ ] Orchestration logic
- [ ] Error handling

#### 5.1.2 UI Converter
**File: `src/dazzle_dnr_ui/converters/workspace_converter.py`**
- [ ] Convert `ir.Workspace` → `UISpec.WorkspaceSpec`
- [ ] Use existing layout engine (`src/dazzle/ui/layout_engine/`)
- [ ] Map attention signals to components
- [ ] Generate layout structure

**File: `src/dazzle_dnr_ui/converters/surface_converter.py`**
- [ ] Convert `ir.Surface` → `ComponentSpec`
- [ ] Infer component type from surface kind
- [ ] Map fields to form/table components
- [ ] Generate actions and effects

**File: `src/dazzle_dnr_ui/converters/__init__.py`**
- [ ] `convert_appspec_to_ui(appspec: ir.AppSpec) -> UISpec`
- [ ] Orchestration logic
- [ ] Error handling

#### 5.1.3 Integration
- [ ] Add converter invocation to Dazzle CLI
- [ ] `dazzle convert --to backend` command
- [ ] `dazzle convert --to ui` command
- [ ] Output spec as JSON

#### 5.1.4 Testing
- [ ] Test with `simple_task` example
- [ ] Test with `support_tickets` example
- [ ] Golden master tests for converters
- [ ] Validation of generated specs

### 5.2 Deliverables
- ✅ Working converters from AppSpec to BackendSpec and UISpec
- ✅ CLI commands for conversion
- ✅ Test coverage with real examples
- ✅ Documentation on conversion process

---

## 6. Stage 4: DNR-Back Runtime Implementation

**Goal**: Build native backend runtime (Pydantic models + FastAPI)

**Duration**: 2-3 weeks

### 6.1 Tasks

#### 6.1.1 Model Generation
**File: `src/dazzle_dnr_back/runtime/models.py`**
- [ ] Generate Pydantic models from `EntitySpec`
- [ ] Field type mapping (BackendSpec → Pydantic)
- [ ] Validators and constraints
- [ ] Nested models and relationships
- [ ] Serialization configuration

#### 6.1.2 Service Generation
**File: `src/dazzle_dnr_back/runtime/services.py`**
- [ ] Generate service function stubs from `ServiceSpec`
- [ ] Input/output schemas
- [ ] Business rule enforcement hooks
- [ ] Effect execution framework
- [ ] Domain operation templates (CRUD, custom)

#### 6.1.3 Route Generation
**File: `src/dazzle_dnr_back/runtime/routes.py`**
- [ ] Generate FastAPI routes from `EndpointSpec`
- [ ] Path parameter extraction
- [ ] Request/response models
- [ ] Dependency injection (auth, tenancy)
- [ ] Error handling
- [ ] Rate limiting integration

#### 6.1.4 Persistence Layer
**File: `src/dazzle_dnr_back/runtime/persistence.py`**
- [ ] SQLAlchemy model generation (optional)
- [ ] Alembic migration support
- [ ] In-memory storage (for testing)
- [ ] CRUD repository pattern
- [ ] Transaction management

#### 6.1.5 OpenAPI Generation
**File: `src/dazzle_dnr_back/runtime/openapi.py`**
- [ ] Generate OpenAPI 3.0 spec from BackendSpec
- [ ] Schema definitions
- [ ] Path definitions
- [ ] Authentication schemes
- [ ] Tags and metadata

#### 6.1.6 Runtime Server
**File: `src/dazzle_dnr_back/runtime/server.py`**
- [ ] FastAPI application factory
- [ ] Route registration
- [ ] Middleware setup (auth, CORS, logging)
- [ ] Development server (uvicorn)
- [ ] Configuration management

#### 6.1.7 CLI Integration
- [ ] `dazzle dnr-back serve` - start development server
- [ ] `dazzle dnr-back openapi` - export OpenAPI spec
- [ ] `dazzle dnr-back migrate` - run database migrations

#### 6.1.8 Testing
- [ ] Unit tests for each generator
- [ ] Integration tests with FastAPI TestClient
- [ ] End-to-end tests with database
- [ ] Performance tests

### 6.2 Deliverables
- ✅ Working DNR-Back runtime
- ✅ FastAPI server from BackendSpec
- ✅ OpenAPI generation
- ✅ CLI commands for runtime management
- ✅ Example backend application
- ✅ Documentation and guides

---

## 7. Stage 5: DNR-UI Runtime Implementation

**Goal**: Build native UI runtime (signals + DOM rendering)

**Duration**: 3-4 weeks

### 7.1 Tasks

#### 7.1.1 Component Registry
**File: `src/dazzle_dnr_ui/components/primitives/__init__.py`**
- [ ] Implement all 17 primitive components from DNR-Components-v1 section 1
- [ ] Page, LayoutShell, Card
- [ ] DataTable, SimpleTable
- [ ] Form, Button, IconButton
- [ ] Tabs, TabPanel, Modal, Drawer
- [ ] Toolbar, FilterBar, SearchBox
- [ ] MetricTile, MetricRow
- [ ] SideNav, TopNav, Breadcrumbs

**File: `src/dazzle_dnr_ui/components/patterns/__init__.py`**
- [ ] Implement all 7 pattern components from DNR-Components-v1 section 2
- [ ] FilterableTable
- [ ] SearchableList
- [ ] MasterDetailLayout
- [ ] WizardForm
- [ ] CRUDPage
- [ ] MetricsDashboard
- [ ] SettingsFormPage

#### 7.1.2 State Management
**File: `src/dazzle_dnr_ui/runtime/state_manager.py`**
- [ ] Signals-based state system
- [ ] State scopes (local, workspace, app, session)
- [ ] State subscription and updates
- [ ] Derived state computation
- [ ] Persistence (localStorage/sessionStorage)

#### 7.1.3 View Rendering
**File: `src/dazzle_dnr_ui/runtime/renderer.py`**
- [ ] ViewNode → DOM conversion
- [ ] Binding resolution (prop, state, derived)
- [ ] Conditional rendering
- [ ] Loop rendering
- [ ] Component instantiation
- [ ] Re-rendering optimization

#### 7.1.4 Action Execution
**File: `src/dazzle_dnr_ui/runtime/action_executor.py`**
- [ ] Action dispatch system
- [ ] State transitions
- [ ] Effect execution:
  - [ ] Fetch (backend service calls)
  - [ ] Navigate (routing)
  - [ ] Log (console)
  - [ ] Toast (notifications)
- [ ] Error handling
- [ ] Loading states

#### 7.1.5 Theme Engine
**File: `src/dazzle_dnr_ui/runtime/theme_engine.py`**
- [ ] Theme token application
- [ ] CSS variable generation
- [ ] Variant switching
- [ ] Persona-aware theming
- [ ] Dark mode support

#### 7.1.6 Development Server
**File: `src/dazzle_dnr_ui/runtime/server.py`**
- [ ] Static file server
- [ ] Hot module reloading
- [ ] WebSocket for live updates
- [ ] Development tools UI
- [ ] Error overlay

#### 7.1.7 Workspace Routing
- [ ] Client-side routing
- [ ] Route parameter extraction
- [ ] Navigation guards
- [ ] History management
- [ ] Deep linking

#### 7.1.8 CLI Integration
- [ ] `dazzle dnr-ui serve` - start development server
- [ ] `dazzle dnr-ui build` - build production assets
- [ ] `dazzle dnr-ui component` - scaffold new component

#### 7.1.9 Testing
- [ ] Unit tests for all components
- [ ] State management tests
- [ ] Rendering tests (jsdom)
- [ ] Integration tests
- [ ] Visual regression tests (optional)

### 7.2 Deliverables
- ✅ Working DNR-UI runtime
- ✅ All primitive and pattern components
- ✅ State management system
- ✅ Development server
- ✅ CLI commands
- ✅ Example UI application
- ✅ Documentation and component catalog

---

## 8. Stage 6: Integration & Examples

**Goal**: Integrate DNR-Back and DNR-UI, create example projects

**Duration**: 1-2 weeks

### 8.1 Tasks

#### 8.1.1 Full-Stack Integration
- [ ] Connect DNR-UI frontend to DNR-Back backend
- [ ] API client generation from OpenAPI
- [ ] Authentication flow
- [ ] Error handling
- [ ] Loading states

#### 8.1.2 Example Projects
**simple_task_dnr**:
- [ ] Convert simple_task to DNR
- [ ] BackendSpec + UISpec
- [ ] Full-stack application
- [ ] README with instructions

**support_tickets_dnr**:
- [ ] Convert support_tickets to DNR
- [ ] Multi-entity relationships
- [ ] Complex UI patterns
- [ ] README with instructions

#### 8.1.3 Stack Integration
- [ ] Create `dnr_native` stack in `src/dazzle/stacks/`
- [ ] Generate DNR specs as build artifacts
- [ ] Integration with existing Dazzle workflow
- [ ] `dazzle build --stack dnr_native`

#### 8.1.4 Documentation
- [ ] DNR architecture guide
- [ ] BackendSpec reference
- [ ] UISpec reference
- [ ] Component catalog
- [ ] MCP usage guide
- [ ] Migration guide from existing stacks

#### 8.1.5 Testing
- [ ] End-to-end tests for example projects
- [ ] Full-stack integration tests
- [ ] LLM-driven development tests (via MCP)

### 8.2 Deliverables
- ✅ Two complete DNR example projects
- ✅ `dnr_native` stack in Dazzle
- ✅ Comprehensive documentation
- ✅ Test coverage for integration scenarios

---

## 9. Testing Strategy

### 9.1 Unit Tests
- All spec types (Pydantic validation)
- All converters
- All generators
- All components
- State management
- Action execution

### 9.2 Integration Tests
- AppSpec → BackendSpec/UISpec conversion
- BackendSpec → FastAPI server
- UISpec → Rendered UI
- MCP tool interactions
- Full-stack flows

### 9.3 Example-Based Tests
- Generate specs from `simple_task`
- Generate specs from `support_tickets`
- Run DNR-Back server
- Run DNR-UI server
- Verify end-to-end functionality

### 9.4 Golden Master Tests
- Spec generation outputs
- Generated OpenAPI schemas
- Component rendering outputs

### 9.5 LLM Interaction Tests
- MCP tool calls
- Spec creation via LLM
- Spec modification via LLM
- Component composition via LLM

---

## 10. Success Metrics

### 10.1 Stage 1 (Specs)
- ✅ 100% of BackendSpec types implemented
- ✅ 100% of UISpec types implemented
- ✅ >90% test coverage
- ✅ JSON schema generation working

### 10.2 Stage 2 (MCP)
- ✅ All 9 MCP tools implemented
- ✅ MCP protocol compliance
- ✅ Component registry functional
- ✅ LLM can query and manipulate specs

### 10.3 Stage 3 (Converters)
- ✅ `simple_task` converts successfully
- ✅ `support_tickets` converts successfully
- ✅ Generated specs validate
- ✅ CLI commands functional

### 10.4 Stage 4 (DNR-Back)
- ✅ FastAPI server runs from BackendSpec
- ✅ OpenAPI spec generated
- ✅ CRUD operations work
- ✅ Auth and tenancy enforced
- ✅ Example backend serves requests

### 10.5 Stage 5 (DNR-UI)
- ✅ All 24 components render
- ✅ State management works across scopes
- ✅ Actions and effects execute
- ✅ Themes apply correctly
- ✅ Development server runs
- ✅ Example UI displays

### 10.6 Stage 6 (Integration)
- ✅ Full-stack examples work end-to-end
- ✅ `dazzle build --stack dnr_native` succeeds
- ✅ Documentation complete
- ✅ MCP-driven development demonstrated

---

## 11. Risk Mitigation

### 11.1 Technical Risks

**Risk**: Spec types too complex or verbose
- **Mitigation**: Start with minimal viable specs, iterate based on real examples

**Risk**: State management complexity in DNR-UI
- **Mitigation**: Use proven patterns (signals), keep scopes simple

**Risk**: Performance issues with DOM rendering
- **Mitigation**: Optimize rendering with Virtual DOM or diffing, benchmark early

**Risk**: MCP interface too limited for real LLM workflows
- **Mitigation**: Test with real LLM agents during Stage 2, iterate tools

### 11.2 Integration Risks

**Risk**: Converters can't handle all AppSpec patterns
- **Mitigation**: Start with simple examples, add coverage incrementally

**Risk**: Breaking changes to existing Dazzle stacks
- **Mitigation**: Parallel evolution, no modifications to existing stacks

**Risk**: Package dependency conflicts in monorepo
- **Mitigation**: Careful dependency management, shared requirements.txt

### 11.3 Scope Risks

**Risk**: DNR implementation takes longer than estimated
- **Mitigation**: Prioritize core functionality, defer advanced features

**Risk**: Feature creep (too many components, too many MCP tools)
- **Mitigation**: Stick to spec v1, defer v2 features

---

## 12. Dependencies

### 12.1 External Dependencies

**DNR-Back**:
- FastAPI (^0.104.0)
- Pydantic (^2.5.0)
- SQLAlchemy (^2.0.0) - optional
- Alembic (^1.12.0) - optional
- uvicorn (^0.24.0)

**DNR-UI**:
- Signals library (TBD: preact/signals, solid-js, or custom)
- Web Components API (native browser)
- Routing library (TBD: navigo or custom)
- Optional: Vite for build tooling

**MCP**:
- Existing Dazzle MCP server (`src/dazzle/mcp/`)
- MCP protocol (already integrated)

### 12.2 Internal Dependencies

- `dazzle.core.ir` - AppSpec types
- `dazzle.ui.layout_engine` - Layout planning (for converters)
- `dazzle.stacks.base` - Stack interface (for `dnr_native` stack)
- `dazzle.mcp` - MCP server extensions

---

## 13. Open Questions

### 13.1 Technical Decisions

1. **State management library for DNR-UI**: Custom signals implementation or use existing (preact/signals, solid-js)?
   - **Recommendation**: Start with custom minimal implementation, evaluate libraries if complexity grows

2. **Rendering approach**: Web Components, React-like Virtual DOM, or direct DOM manipulation?
   - **Recommendation**: Web Components for component isolation, direct DOM for simplicity

3. **Build tooling for DNR-UI**: Vite, esbuild, or custom?
   - **Recommendation**: Vite for development server + HMR, esbuild for production builds

4. **Persistence layer for DNR-Back**: SQLAlchemy mandatory or optional?
   - **Recommendation**: Optional, start with in-memory for simplicity

5. **OpenAPI generation**: Standalone or use FastAPI's built-in?
   - **Recommendation**: Use FastAPI's built-in, augment with BackendSpec metadata

### 13.2 Design Decisions

1. **Component composition**: Allow custom components or only built-in registry?
   - **Recommendation**: Start with built-in only, add custom later in v2

2. **Theme customization**: Token-based only or allow CSS overrides?
   - **Recommendation**: Token-based for v1, CSS overrides as escape hatch

3. **Backend service implementation**: Stubs only or generate basic CRUD?
   - **Recommendation**: Generate basic CRUD, stubs for custom operations

4. **MCP tool granularity**: Fine-grained (per-field edits) or coarse-grained (whole specs)?
   - **Recommendation**: Coarse-grained for v1, add fine-grained patches in v2

---

## 14. Next Steps

### Immediate Actions (Week 1)
1. **Set up package structure** for `dazzle-dnr-back` and `dazzle-dnr-ui`
2. **Define BackendSpec core types** (EntitySpec, FieldSpec, RelationSpec)
3. **Define UISpec core types** (WorkspaceSpec, ComponentSpec, ViewNode)
4. **Write initial tests** for spec validation

### Short-term Actions (Weeks 2-3)
1. Complete all spec types
2. Implement MCP tool skeleton
3. Build component registry
4. Create first converter (Entity → EntitySpec)

### Medium-term Actions (Weeks 4-8)
1. Implement DNR-Back runtime
2. Implement DNR-UI runtime
3. Build example projects
4. Write documentation

### Long-term Actions (Weeks 9-12)
1. Integration testing
2. Performance optimization
3. LLM-driven development demos
4. Public release preparation

---

## 15. Appendix

### 15.1 Reference Documents
- DNR-Spec-v1.md
- DNR-Components-v1.md
- DNR-MCP-Spec-v1.md
- Dazzle DSL Reference (docs/DAZZLE_DSL_REFERENCE_0_1.md)
- Dazzle IR Reference (docs/DAZZLE_IR_0_1.md)

### 15.2 Related Work
- Existing Dazzle stacks (`src/dazzle/stacks/`)
- Layout engine (`src/dazzle/ui/layout_engine/`)
- MCP server (`src/dazzle/mcp/`)
- Next.js semantic stack (`src/dazzle/stacks/nextjs_semantic/`)

### 15.3 Future Extensions (Post-v1)
- GraphQL support (alternative to FastAPI)
- React builder (UISpec → React components)
- Django/DRF builder (BackendSpec → Django)
- Real-time sync (WebSockets, SSE)
- Multi-user collaborative editing
- Visual component editor
- Drag-and-drop workspace composer

---

**End of DNR Implementation Plan v1**
