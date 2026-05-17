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
    └── PageContext ──→ DNR-UI ──→ HTMX Templates
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
- FastAPI is the current backend
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
   - CRUD operations with PostgreSQL persistence
   - Custom operations with handlers
   - Business rule enforcement

3. **FastAPI Routes** from EndpointSpec
   - RESTful endpoints
   - Request/response validation
   - OpenAPI documentation

## Frontend Architecture (DNR-UI)

### Design Decision: Server-Rendered HTMX

**Why server-rendered templates over client-side JS**:
- Server is the single source of truth — no client/server state sync
- HTMX declarative attributes replace custom JavaScript
- Vanilla JS handles ephemeral UI state (toggles, modals, transitions)
- Zero build toolchain — two CDN script tags, no node_modules
- LLM-friendly — templates are plain HTML with predictable attributes

### Template Pipeline

```
AppSpec (Dazzle IR)
    ↓ template_compiler
PageContext (Pydantic model)
    ↓ Jinja2
HTML + hx-* attributes
    ↓ browser
HTMX swaps partial HTML from server
```

### Technology Stack

| Technology | Role |
|-----------|------|
| **HTMX** | Declarative server interactions (`hx-get`, `hx-post`, `hx-swap`) |
| **Dazzle CSS** | Bundled native stylesheet (`/styles/dazzle.css`) — tokens + components in @layer order, no third-party CSS framework |
| **dz.js** | Lightweight client-side state (modals, toggles, transitions) |
| **Jinja2** | Server-side template rendering |

> The workspace runtime no longer loads Tailwind or DaisyUI. Site/marketing
> pages still consume the legacy CDN tags via `site_renderer.get_shared_head_html`
> for back-compat with `stat-value` / `bg-base-*` class names — see
> `docs/CSS_MIGRATION_GUIDE.md` for the rename map.

### Template Structure

```
templates/
├── layouts/             # Page shells (app_shell, single_column)
├── components/          # Full-page components (filterable_table, form, detail_view)
├── fragments/           # Partial HTML for HTMX swaps (table_rows, inline_edit, bulk_actions)
└── macros/              # Reusable Jinja2 macros
```

- **Layouts** wrap pages with nav, head, and CDN script tags
- **Components** render full content areas from a `PageContext`
- **Fragments** return partial HTML — the unit of HTMX interaction
- **Macros** are Jinja2 helpers for repeated markup patterns

### Fragment Rendering

Fragments are the key interaction primitive. When HTMX fires a request, the server renders a fragment and returns partial HTML:

```python
# In a FastAPI route handler
@app.get("/_dazzle/tasks")
async def list_tasks(request: Request, search: str = ""):
    rows = filter_tasks(search)
    return templates.TemplateResponse(
        "fragments/table_rows.html",
        {"request": request, "table": table_context, "rows": rows}
    )
```

The browser swaps the fragment into the target element — no full page reload.

### Interaction Patterns

| Pattern | Technology | Fragment |
|---------|-----------|----------|
| **Search with debounce** | HTMX `hx-trigger="keyup changed delay:300ms"` | `search_input.html` |
| **Inline editing** | HTMX `hx-put` + JS toggle state | `inline_edit.html` |
| **Bulk actions** | JS selection state + HTMX submit | `bulk_actions.html` |
| **Slide-over detail** | CSS transitions + HTMX content load | `slide_over.html` |
| **Form submission** | HTMX `hx-post` with validation fragments | `form.html` + `form_errors.html` |
| **Pagination** | HTMX `hx-get` with page parameter | `table_pagination.html` |

## Conversion Pipeline

### AppSpec → BackendSpec

```python
from dazzle_back.converters import convert_appspec_to_backend

backend_spec = convert_appspec_to_backend(appspec)
```

Transforms:
- `EntitySpec` → `BackendEntitySpec` with field types
- `SurfaceSpec` → `ServiceSpec` + `EndpointSpec`
- Infers CRUD operations from surface modes

### AppSpec → UISpec

```python
from dazzle_ui.converters import convert_appspec_to_ui

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

- PostgreSQL with async drivers (asyncpg)
- Async route handlers
- Pydantic validation caching
- Auto-migration on startup

### Frontend

- No virtual DOM (direct DOM manipulation)
- Fine-grained signal subscriptions
- CSS variables for theme switching (no recomputation)
- Lazy component rendering

## Future Directions

- **Mobile runtime**: UISpec → React Native / Flutter
- **WebSocket support**: Real-time updates in specs
