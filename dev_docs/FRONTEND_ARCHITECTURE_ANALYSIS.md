# DNR Frontend Architecture Analysis

**Date**: 2025-11-29
**Status**: Deep Dive Complete
**Conclusion**: The DSL and AppSpec **DO support the goals** - the gap is in the DNR UI infrastructure

## Executive Summary

The DAZZLE DSL and IR layer are well-designed and semantically rich. The problem lies entirely in the **DNR UI generation pipeline**, which fails to:
1. Connect surfaces to the JavaScript runtime
2. Generate proper UISpec from AppSpec
3. Deliver a functional user interface despite having all the semantic information

**Recommendation**: Improve DNR infrastructure, not DSL grammar.

## Analysis of Key Artifacts

### 1. DSL Grammar (SUPPORTS GOALS)

The DSL is well-designed with rich semantics:

```dsl
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    ...
```

**Strengths**:
- Surface modes (list, view, create, edit) map clearly to UI patterns
- Entity references connect data to views
- Field definitions provide schema for forms/tables
- UX blocks add filtering, sorting, attention signals
- Workspaces provide composition of multiple views

### 2. AppSpec IR (SUPPORTS GOALS)

The IR (`src/dazzle/core/ir.py`) is comprehensive:

- `SurfaceSpec`: Contains mode, entity_ref, sections with elements
- `SurfaceSection`: Groups fields with labels
- `SurfaceElement`: Individual field with label and options
- `UXSpec`: Purpose, show/sort/filter/search semantics
- `WorkspaceSpec`: Regions with source, filter, aggregates

**Strengths**:
- Complete type system with Pydantic models
- All UI-relevant information is captured
- Clear separation between domain (entities) and presentation (surfaces)

### 3. DNR UI Conversion Layer (PARTIAL IMPLEMENTATION)

`src/dazzle_dnr_ui/converters/surface_converter.py`:
- `_surface_mode_to_component()` maps modes to component types
- `_generate_view()` creates ElementNode trees
- `_generate_form_fields()` creates Input components

**Issue Identified**: The conversion produces valid component specs but:
- Components have empty/minimal views
- Form fields are generated but not connected to state
- List surfaces produce `FilterableTable` but no column configuration

### 4. JavaScript Runtime (PARTIAL IMPLEMENTATION)

`src/dazzle_dnr_ui/runtime/static/js/components.js`:
- Has `FilterableTable`, `DataTable`, `Form`, `Input` components
- Components accept props and render DOM elements

`src/dazzle_dnr_ui/runtime/static/js/app.js`:
- `createApp()` registers components from UISpec
- Route matching works
- Component rendering via `renderViewNode`

**Critical Gap Identified**: The `uiSpec` passed to the JS app has:
- **0 components** - components are not being generated
- **Empty workspaces** - routes exist but reference non-existent components

## Root Cause Analysis

### The Gap: AppSpec → UISpec Conversion

The pipeline is:
```
DSL → Parser → AppSpec (IR) → UISpec Converter → UISpec → JS Runtime → DOM
                               ^^^^^^^^^^^^^^^^^^^^
                               THIS IS BROKEN
```

**Problem 1**: The server (`dazzle_dnr_back/runtime/server.py`) exposes `/api/tasks` but doesn't expose the UISpec endpoint. The frontend JS gets an empty spec.

**Problem 2**: Even when conversion runs, the generated ComponentSpec has minimal view trees:
- Forms lack actual input bindings
- Tables lack column definitions
- No data fetching logic connects to API

**Problem 3**: CSS is minimal - no professional styling framework.

## Recommended Solution Path

### Phase 1: Fix UISpec Generation (Critical)

1. **Add UISpec endpoint to backend server**:
   - Expose `/api/ui-spec` that returns the full UISpec
   - Include components, workspaces, routes

2. **Fix surface_converter.py**:
   - Generate complete ElementNode trees with proper props
   - Add data bindings for forms (connect to state)
   - Add column definitions for tables (from entity fields)

3. **Fix workspace_converter.py**:
   - Generate complete route specs
   - Connect routes to generated components

### Phase 2: Enhance JavaScript Runtime

1. **Add API client integration**:
   - Components should fetch data on mount
   - Forms should POST/PUT on submit
   - Tables should load items from `/api/{entity}`

2. **Add state management**:
   - Form state bindings
   - Table pagination/filtering state

### Phase 3: Professional Styling with Tailwind CSS

1. **Integrate Tailwind** into the generated HTML
2. **Update components.js** to use Tailwind classes
3. **Create design tokens** that map to Tailwind

### Phase 4: Docker-First Infrastructure

1. **Refactor `dazzle dnr serve`**:
   - Default: Run in Docker container
   - `--local` flag: Run locally without Docker
   - Container includes: Python backend + static frontend

## Comparison: What Works vs What's Broken

| Layer | Status | Issue |
|-------|--------|-------|
| DSL Parser | WORKS | Produces valid AppSpec |
| AppSpec IR | WORKS | Complete semantic model |
| Backend API | WORKS | `/api/tasks` CRUD works |
| UISpec Generation | BROKEN | Components not generated |
| UISpec Endpoint | MISSING | No `/api/ui-spec` route |
| JS Components | EXISTS | Components defined but not used |
| JS App Bootstrap | BROKEN | Gets empty UISpec |
| CSS Styling | MINIMAL | No professional framework |

## Conclusion

**The fundamental artifacts (DSL, AppSpec, domain patterns) DO support the goals.**

The issue is implementation gaps in the DNR UI infrastructure:
1. UISpec generation doesn't fully transform AppSpec to renderable components
2. Backend doesn't expose UISpec to frontend
3. Frontend gets empty spec and renders nothing useful

This is a **solvable engineering problem**, not a design flaw.

## Next Steps

1. [x] UISpec endpoint already exists (combined_server.py serves `/ui-spec.json`)
2. [x] Fix `surface_converter.py` to generate complete component views (completed 2025-11-29)
3. [x] Fix `workspace_converter.py` to generate complete routes (already working)
4. [x] Verify UISpec reaches JS runtime (completed 2025-11-29)
5. [ ] Integrate Tailwind CSS
6. [x] Add Docker-first infrastructure (completed 2025-11-29)

## Data Flow Fixes (Implemented 2025-11-29)

The following fixes were made to enable the complete data flow:

### 1. Surface Converter - Column Generation

Added `_generate_table_columns()` function to `src/dazzle_dnr_ui/converters/surface_converter.py`:
- Extracts columns from surface sections or entity fields
- Returns column definitions: `[{"key": "field_name", "label": "Field Label"}, ...]`

Updated `_generate_view()` for LIST surfaces:
- Added `columns` prop with column definitions from entity
- Added `apiEndpoint` prop with `/api/{entity}s` URL

### 2. FilterableTable Auto-Fetch

Updated `FilterableTable` component in `src/dazzle_dnr_ui/runtime/static/js/components.js`:
- Accepts `columns` and `apiEndpoint` props from UISpec
- Auto-fetches data from API on mount
- Handles loading, error, and empty states
- Supports paginated responses (`{items: [...]}`)
- Listens for `dnr-delete` events to refresh after deletes

### Data Flow Now Complete

```
DSL Surface Definition
    ↓
Parser → SurfaceSpec (with sections, elements)
    ↓
surface_converter.py → ComponentSpec with:
  - columns: [{key, label}, ...]
  - apiEndpoint: /api/tasks
    ↓
UISpec (embedded in app.js)
    ↓
FilterableTable component renders:
  - Fetches from apiEndpoint
  - Renders DataTable with columns
  - Shows data from API
```

### Updated Status Table

| Layer | Status | Notes |
|-------|--------|-------|
| DSL Parser | WORKS | Produces valid AppSpec |
| AppSpec IR | WORKS | Complete semantic model |
| Backend API | WORKS | `/api/tasks` CRUD works |
| UISpec Generation | WORKS | Components generated with columns |
| UISpec Endpoint | WORKS | `/ui-spec.json` served by combined_server |
| JS Components | WORKS | FilterableTable auto-fetches data |
| JS App Bootstrap | WORKS | UISpec embedded in generated app.js |
| CSS Styling | MINIMAL | No professional framework (Tailwind pending) |

## Docker-First Infrastructure (Implemented)

The `dazzle dnr serve` command now uses a docker-first approach:

### Usage

```bash
# Default: runs in Docker container
dazzle dnr serve

# Run locally without Docker
dazzle dnr serve --local

# Force rebuild of Docker image
dazzle dnr serve --rebuild

# With test endpoints enabled
dazzle dnr serve --test-mode
```

### Implementation

- `src/dazzle_dnr_ui/runtime/docker_runner.py` - Docker runner module
- Generates Dockerfile on-the-fly from project DSL
- Builds and runs container with proper port mapping
- Falls back to local execution if Docker unavailable

### Benefits

1. **Consistent Environment**: All developers use the same runtime
2. **No Local Dependencies**: Don't need Python, FastAPI, etc. installed
3. **Isolated Database**: SQLite runs inside container
4. **Easy Cleanup**: Just stop the container
