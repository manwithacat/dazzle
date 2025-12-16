# DNR Architecture

How Dazzle Native Runtime works internally.

## Overview

DNR transforms your Dazzle DSL into working applications through a multi-stage pipeline:

```
DSL Files (.dsl)
    ↓ parse
AppSpec (Dazzle IR)
    ↓ convert
    ├── BackendSpec ──→ DNR-Back ──→ FastAPI App
    └── UISpec ──→ DNR-UI ──→ JavaScript Runtime
```

## Core Principles

### 1. Spec-First

**BackendSpec** and **UISpec** are the source of truth:
- Language-agnostic specifications
- Multiple runtimes can consume them
- No framework lock-in

### 2. LLM-First

Specifications are structured for:
- Deterministic generation
- Easy patching by LLMs
- Semantic clarity

### 3. Framework-Agnostic

Backend and frontend frameworks are outputs, not inputs:
- FastAPI is one possible backend (Django planned)
- Pure JS is the frontend (React optional)

## Backend Architecture (DNR-Back)

### Layers

```
BackendSpec (language-agnostic specification)
    ↓
Runtime Generators
    ├── Model Generator → Pydantic models
    ├── Service Generator → CRUD + custom services
    ├── Route Generator → FastAPI routes
    └── Server → Complete FastAPI application
```

### BackendSpec Structure

```python
BackendSpec:
    name: str
    version: str
    entities: list[EntitySpec]      # Data models
    services: list[ServiceSpec]     # Business logic
    endpoints: list[EndpointSpec]   # HTTP routes
    auth_rules: list[AuthRuleSpec]  # Security
```

### Runtime Generation

The runtime generates:

1. **Pydantic Models** from EntitySpec
   - Field types mapped to Python types
   - Validators from constraints
   - Create/Update schemas auto-generated

2. **Services** from ServiceSpec
   - CRUD operations with in-memory storage
   - Custom operations with handlers
   - Business rule enforcement

3. **FastAPI Routes** from EndpointSpec
   - RESTful endpoints
   - Request/response validation
   - OpenAPI documentation

## Frontend Architecture (DNR-UI)

### Design Decision: Pure JavaScript

**Why pure JS (no React/Vue)**:
- Maximum control over rendering
- Minimum bundle size
- No build step required
- Easy to understand and modify
- Aligns with LLM-first architecture

### Layers

```
UISpec (declarative specification)
    ↓
Runtime Modules
    ├── Signals → Reactive state primitives
    ├── State Manager → Scoped state (local/workspace/app)
    ├── Renderer → ViewNode → DOM
    ├── Components → Reusable UI elements
    ├── Actions → Event handling
    └── Theme Engine → CSS variables
```

### UISpec Structure

```python
UISpec:
    name: str
    workspaces: list[WorkspaceSpec]   # Pages/layouts
    components: list[ComponentSpec]    # Reusable UI
    themes: list[ThemeSpec]           # Styling
    default_theme: str
```

### Signals-Based Reactivity

DNR-UI uses a lightweight signals pattern:

```javascript
// Create reactive state
const [count, setCount] = createSignal(0);

// Automatic updates
createEffect(() => {
    document.getElementById('counter').textContent = count();
});

// Update triggers re-render
setCount(count() + 1);
```

Benefits:
- No virtual DOM overhead
- Fine-grained reactivity
- Simple mental model

### State Scopes

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `local` | Component | Form fields, toggles |
| `workspace` | Page/workspace | Filters, selections |
| `app` | Application | User settings, auth |
| `session` | Browser session | Temporary preferences |

### View Rendering

ViewNodes are rendered to DOM:

```python
# UISpec ViewNode
ElementNode(
    tag="div",
    props={"class": LiteralBinding("card")},
    children=[
        ElementNode(tag="h2", children=[...]),
        ConditionalNode(condition=..., then_branch=..., else_branch=...),
        LoopNode(source=..., item_name="task", body=...)
    ]
)
```

Becomes:
```html
<div class="card">
    <h2>...</h2>
    <!-- conditional content -->
    <!-- loop content -->
</div>
```

## Output Formats

### Vite (Production)

Complete project with ES modules:

```
src/
├── dnr/
│   ├── signals.js      # createSignal, createEffect, createMemo
│   ├── state.js        # StateManager, scoped state
│   ├── dom.js          # createElement, text, attr utilities
│   ├── bindings.js     # resolveBinding for data binding
│   ├── components.js   # ComponentRegistry
│   ├── renderer.js     # renderViewNode, patch updates
│   ├── theme.js        # ThemeEngine, CSS variables
│   ├── actions.js      # ActionDispatcher
│   ├── app.js          # createApp initialization
│   └── index.js        # Main exports
├── main.js             # Application entry
└── ui-spec.json        # Generated specification
```

### JS (Development)

Split files for quick iteration:

```
├── index.html
├── dnr-runtime.js      # Combined runtime (IIFE)
├── app.js              # Application bootstrap
└── ui-spec.json        # Generated specification
```

### HTML (Preview)

Single self-contained file:

```html
<!DOCTYPE html>
<html>
<head>
    <style>/* Theme CSS */</style>
</head>
<body>
    <div id="app"></div>
    <script>/* DNR Runtime */</script>
    <script>/* UI Spec */</script>
    <script>/* App Bootstrap */</script>
</body>
</html>
```

## Conversion Pipeline

### AppSpec → BackendSpec

```python
from dazzle_dnr_back.converters import convert_appspec_to_backend

backend_spec = convert_appspec_to_backend(appspec)
```

Transforms:
- `EntitySpec` → `BackendEntitySpec` with field types
- `SurfaceSpec` → `ServiceSpec` + `EndpointSpec`
- Infers CRUD operations from surface modes

### AppSpec → UISpec

```python
from dazzle_dnr_ui.converters import convert_appspec_to_ui

ui_spec = convert_appspec_to_ui(appspec)
```

Transforms:
- `WorkspaceSpec` → `UIWorkspaceSpec` with layouts
- `SurfaceSpec` → `ComponentSpec` with views
- Generates default theme from app metadata

## Extensibility

### Adding New Runtimes

Backend runtimes implement:
```python
def create_app(spec: BackendSpec) -> Application:
    """Generate application from BackendSpec."""
```

UI runtimes implement:
```python
def generate(spec: UISpec, output_dir: str) -> list[Path]:
    """Generate UI artifacts from UISpec."""
```

### Custom Components

Register custom components in UISpec:
```python
ComponentSpec(
    name="CustomWidget",
    category="custom",
    props_schema=PropsSchema(fields=[...]),
    view=ElementNode(...)
)
```

## Performance Considerations

### Backend

- In-memory storage by default (plug in database adapters)
- Async route handlers
- Pydantic validation caching

### Frontend

- No virtual DOM (direct DOM manipulation)
- Fine-grained signal subscriptions
- CSS variables for theme switching (no recomputation)
- Lazy component rendering

## Future Directions

- **Django adapter**: BackendSpec → Django/DRF
- **React builder**: UISpec → React components
- **Mobile runtime**: UISpec → React Native / Flutter
- **WebSocket support**: Real-time updates in specs
