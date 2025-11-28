# Evaluation: DNR-SeparationOfConcerns-v1

**Document**: `/Volumes/SSD/Dazzle/dev_docs/DNR-SeparationOfConcerns-v1.md`
**Date**: 2025-11-28
**Context**: Post-stack-retirement, DNR is now the primary runtime target

---

## Executive Summary

**Verdict**: This document is excellent and should become a cornerstone of DNR development.

The separation of concerns model is well-thought-out and aligns perfectly with our pivot from "generate code for frameworks" to "run apps directly from specs." With DNR as the native target, we can now **enforce** these separations at the DSL/parser level rather than hoping generated code follows patterns.

---

## Key Strengths

### 1. Clean Three-Layer Model

```
Domain/Backend → Behaviour → UI
```

This is the right abstraction. Each layer has clear responsibilities:
- **Backend**: Data integrity, business rules, auth
- **Behaviour**: State transitions, orchestration, effects
- **UI**: Visual structure, binding, presentation

The explicit "does not" lists are particularly valuable - they prevent layer bleeding.

### 2. Component Roles

```typescript
type ComponentRole = "presentational" | "controller" | "page";
```

This is a proven pattern (React smart/dumb components) but applied at the **spec level**. Benefits:
- Validates at parse time, not runtime
- Guides LLM generation (default to presentational)
- Makes refactoring explicit

### 3. Pure vs Impure Actions

```typescript
type ActionKind = "pure" | "impure";
```

This is the key insight for DNR. By making purity explicit:
- Pure actions can be optimized (memoization, batching)
- Impure actions are the only boundary points
- Testing becomes trivial (pure = unit test, impure = mock effects)

### 4. Effect Boundaries

The rule that "Views cannot directly call backend services" is critical. All backend access goes through:
```
View → dispatch Action → Effect (fetch) → Backend
```

This creates a single integration point that's easy to:
- Log and audit
- Mock for testing
- Intercept for offline support

---

## Opportunities for Enhancement

### 1. Make It DSL-Native

The document describes TypeScript types. With DNR as the target, we should express these in the DSL directly:

```dsl
# Current (implicit)
component TaskCard:
  view:
    ...

# Proposed (explicit role)
component TaskCard:
  role: presentational
  props:
    task: Task
    onSelect: action
  view:
    ...

# Actions with explicit purity
action selectTask: pure
  selected = task

action loadTasks: impure
  effect: fetch GET /tasks
  onSuccess: setTasks
```

### 2. Access Control Integration

The document mentions "authorization at the service/endpoint level" but doesn't detail it. We should add:

```dsl
entity Task:
  owner: ref User required

  access:
    create: authenticated
    read: owner = current_user
    update: owner = current_user
    delete: owner = current_user and status = "draft"
```

This makes authorization declarative and enforceable.

### 3. Derived State

The binding types include `derived`:
```typescript
{ kind: "derived"; expr: string }
```

We should define what expressions are allowed:
- Pure functions of other state
- No side effects
- Memoizable

```dsl
state:
  tasks: Task[]
  filter: enum[all,active,done] = all

  # Derived - computed from other state
  filteredTasks: derived
    when filter = "all": tasks
    when filter = "active": tasks where status != "done"
    when filter = "done": tasks where status = "done"
```

### 4. Effect Types

The document lists four effect kinds:
- `fetch` - API calls
- `navigate` - routing
- `log` - logging
- `toast` - notifications

We should add:
- `persist` - local storage
- `subscribe` - WebSocket/SSE
- `file` - file operations
- `clipboard` - copy/paste

### 5. Validation Error Messages

The validation rules are good but should have friendly error messages:

```
Error: Presentational component 'TaskCard' cannot own state.

  component TaskCard:
    role: presentational
    state:           # ← Not allowed
      selected: Task

  Hint: Use role: controller if this component needs local state,
        or lift state to a parent controller component.
```

---

## Integration with v0.4.0 Roadmap

### Phase 1 (Vertical)

The separation model guides implementation:
1. **Backend Runtime**: Implement `BackendSpec` → FastAPI (no UI concepts)
2. **Frontend Runtime**: Implement `UISpec` → Preact (no direct backend calls)
3. **Behaviour Layer**: Bridge via Effects

### Phase 2 (Horizontal)

Features map to layers:
- **Auth**: Backend layer + UI bindings
- **File Uploads**: Effect type + Backend storage
- **Real-time**: Effect type (subscribe)

### Phase 3 (Meta)

Dev tools respect boundaries:
- State inspector shows Behaviour layer
- Network tab shows Effect executions
- Component tree shows UI layer with roles

---

## Proposed DSL Changes

### 1. Component Role Declaration

```dsl
# Presentational - view only
component Badge:
  role: presentational
  props:
    text: str
    variant: enum[default,success,warning,error] = default
  view:
    span class="badge badge-{variant}": text

# Controller - owns state and actions
component TaskFilter:
  role: controller
  state:
    filter: enum[all,active,done] = all
  actions:
    setFilter(f): pure
      filter = f
  view:
    ButtonGroup:
      Button "All" active={filter = "all"} onClick={setFilter("all")}
      Button "Active" active={filter = "active"} onClick={setFilter("active")}
      Button "Done" active={filter = "done"} onClick={setFilter("done")}

# Page - workspace entry point
component TasksPage:
  role: page
  workspace: tasks_workspace
  view:
    PageLayout:
      TaskFilter
      TaskList
```

### 2. Action Purity

```dsl
actions:
  # Pure - synchronous state update
  selectTask(task): pure
    selectedTask = task

  # Pure - toggle
  toggleSidebar: pure
    sidebarOpen = not sidebarOpen

  # Impure - has effect
  loadTasks: impure
    isLoading = true
    effect: fetch GET /tasks
    onSuccess(data):
      tasks = data
      isLoading = false
    onError(err):
      error = err.message
      isLoading = false

  # Impure - navigation
  viewTask(id): impure
    effect: navigate /tasks/{id}
```

### 3. Effect Declaration

```dsl
effects:
  # Fetch with typed response
  fetchTasks:
    kind: fetch
    method: GET
    endpoint: /tasks
    response: Task[]

  # Mutation
  createTask:
    kind: fetch
    method: POST
    endpoint: /tasks
    body: TaskCreate
    response: Task

  # Navigation
  goToTask:
    kind: navigate
    route: /tasks/{id}

  # Toast notification
  showSuccess:
    kind: toast
    variant: success
```

---

## Validation Rules to Implement

### Parser-Level (Syntax)

1. `role` is required on all `component` blocks
2. `kind` (pure/impure) is required on all `action` blocks
3. `effect` can only appear in `impure` actions

### Linker-Level (References)

1. Presentational components cannot reference `state`, `workspaceState`, `appState`
2. `effect.backendService` must reference valid `ServiceSpec`
3. `effect.navigate` route must match a `workspace`

### Lint-Level (Best Practices)

1. Page components should use layout primitives
2. Controllers should compose presentationals (not raw markup)
3. Warn on deep component nesting (> 5 levels)

---

## Conclusion

DNR-SeparationOfConcerns-v1 provides an excellent foundation for the next phase of Dazzle. By making these concepts first-class in the DSL:

1. **Enforceability**: Validation at parse time, not runtime
2. **LLM Guidance**: Clear rules for generation
3. **Testability**: Pure/impure separation enables easy testing
4. **Maintainability**: Layer boundaries prevent spaghetti

**Recommendation**: Incorporate these concepts into the DSL grammar and IR as part of Phase 1 of the v0.4.0 roadmap.

---

## Next Steps

1. [ ] Add `role` field to `component` in DSL grammar
2. [ ] Add `kind` field to `action` in DSL grammar
3. [ ] Add `access` block to `entity` in DSL grammar
4. [ ] Implement validation rules in parser/linker
5. [ ] Update documentation with new syntax
6. [ ] Create examples demonstrating separation
