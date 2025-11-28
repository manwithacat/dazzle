# DNR-SeparationOfConcerns-v1

## Project: Dazzle Native Runtimes (DNR)
### Topic: Opinionated Separation of Concerns in the DSL and Runtime

This document refines the DNR specs to enforce a clearer separation of concerns between:

1. **Domain / Backend** – entities, services, endpoints.
2. **Application State & Behaviour** – state atoms, pure/impure actions, effects.
3. **UI Structure & Presentation** – workspaces, layouts, components, view trees, themes.

The goal is to:

- Make the Dazzle DSL more opinionated.
- Reduce opportunities for cross-layer leakage (e.g. views talking directly to backend).
- Provide a cleaner mental model for LLM-first development and codegen.

---

## 1. Layers and Responsibilities

### 1.1 Domain / Backend Layer (BackendSpec)

- Defines:
  - `EntitySpec` – entities, fields, relationships, constraints.
  - `ServiceSpec` – operations on entities and domain logic.
  - `EndpointSpec` – HTTP/transport mapping of services.
- Responsible for:
  - Data integrity.
  - Business rules.
  - Authorisation & multi-tenancy at the service/endpoint level.
- Explicitly **does not**:
  - Reference UI components.
  - Encode presentation details.

### 1.2 Behaviour Layer (State, Actions, Effects)

- Defines:
  - `StateSpec` – state atoms/signals and their scopes.
  - `ActionSpec` – named operations on state (pure or impure).
  - `EffectSpec` – side-effects that cross the boundary (API calls, navigation, logging).
- Responsible for:
  - State transitions and application logic.
  - Orchestration of backend calls.
- Explicitly **does not**:
  - Render UI directly.
  - Contain DOM or platform-specific concepts.

### 1.3 UI Structure Layer (UISpec)

- Defines:
  - `WorkspaceSpec` – logical pages/routes and layouts.
  - `ComponentSpec` – components, view trees, and roles.
  - `ViewNode` – structural tree of elements/components.
  - Theme and layout metadata.
- Responsible for:
  - Visual structure of the app.
  - Binding view fields to props and state.
- Explicitly **does not**:
  - Encode business logic.
  - Directly call backend services.

---

## 2. Component Roles

To strengthen separation within the UI, components are assigned explicit roles.

### 2.1 ComponentRole

```ts
type ComponentRole =
  | "presentational"   // view-only; props in, events out
  | "controller"       // wires state, actions, and child components
  | "page";            // top-level workspace/page entry, route-bound
```

### 2.2 Extended ComponentSpec

We extend `ComponentSpec` (from DNR-Spec-v1) with `role` and add role-based constraints.

```ts
type ComponentSpec = {
  kind: "component";
  role: ComponentRole;
  name: string;
  propsSchema: SchemaSpec;
  view: ViewNode;
  state?: StateSpec[];
  actions?: ActionSpec[];
  metadata?: Record<string, any>;
};
```

### 2.3 Role Semantics and Constraints

#### 2.3.1 Presentational Components

- **Intent**:
  - Pure view components.
  - Receive data and callbacks via props.
  - Generate no side-effects themselves.

- **Allowed**:
  - `propsSchema` – to describe expected inputs.
  - `view` – may use:
    - `Binding.kind = "literal"`
    - `Binding.kind = "prop"`

- **Disallowed**:
  - `state` – presentational components must not own state directly.
  - `actions` – no actions defined in the component.
  - `Binding.kind = "state" | "workspaceState" | "appState"` – only props/literals.
  - Any direct reference to `EffectSpec` or backend services.

- **Design Pattern**:
  - Equivalent to “dumb/pure/presentational components” in classic React terminology.

#### 2.3.2 Controller Components

- **Intent**:
  - Glue between state, actions, and presentational components.
  - Own and manipulate local or workspace-level state.

- **Allowed**:
  - `state` – can own `StateSpec` with scope `"local"` or `"workspace"`.
  - `actions` – can define both pure and impure `ActionSpec`s.
  - `Binding.kind = "state" | "workspaceState" | "appState" | "prop" | "literal"`.

- **Constraints**:
  - Should primarily compose other components (especially presentational ones).
  - Should *minimise* raw markup in `view` in favour of nested components.
  - Impure actions (see Section 3) are allowed here.

#### 2.3.3 Page Components

- **Intent**:
  - Top-level components associated with routes and workspaces.
  - Orchestrate layout (e.g. sidebars, headers) and select which controllers/presentational components to render.

- **Allowed**:
  - All capabilities of controller components.
  - Binding to `workspaceState` and `appState`.
  - Route-specific metadata via `WorkspaceSpec`.

- **Constraints**:
  - A `WorkspaceSpec` should reference `page` components as entry points.
  - Pages should avoid low-level UI markup; they should use layout primitives (e.g. `LayoutShell`, `Page` from DNR-Components-v1).

---

## 3. Action Kinds: Pure vs Impure

We refine `ActionSpec` to make purity explicit.

### 3.1 ActionKind

```ts
type ActionKind = "pure" | "impure";
```

### 3.2 Extended ActionSpec

```ts
type ActionSpec = {
  name: string;
  kind: ActionKind;
  inputs?: SchemaSpec;
  transitions?: TransitionSpec[];
  effect?: EffectSpec;  // only when kind === "impure"
};
```

### 3.3 Semantics and Constraints

#### 3.3.1 Pure Actions

- **Intent**:
  - Deterministic state updates with no side-effects.

- **Properties**:
  - Must have one or more `TransitionSpec`s (state updates).
  - Must NOT have an `effect` field.

- **Examples**:
  - Updating filters.
  - Selecting a row in a list.
  - Updating form input fields.

#### 3.3.2 Impure Actions

- **Intent**:
  - Boundary between state and side-effects.
  - Typically wrap network calls, navigation, or logging.

- **Properties**:
  - May have transitions (e.g. set `isLoading` flag before a fetch).
  - May have a single `effect` (e.g. `EffectSpec.kind = "fetch"`).

- **Examples**:
  - Loading data from backend services.
  - Saving a form.
  - Navigating to another route.

---

## 4. Effects and Backend Access

We explicitly constrain where backend and navigation can be referenced.

### 4.1 EffectSpec Boundaries

Recall `EffectSpec` (from DNR-Spec-v1):

```ts
type EffectSpec =
  | {
      kind: "fetch";
      backendService: string;  // links to ServiceSpec.name
      onSuccess?: string;      // ActionSpec.name
      onError?: string;        // ActionSpec.name
    }
  | {
      kind: "navigate";
      route: string;
      params?: Record<string, Binding>;
    }
  | {
      kind: "log" | "toast";
      message: Binding;
    };
```

### 4.2 Rules

1. **Backend Access**:
   - Only allowed via `EffectSpec.kind = "fetch"`.
   - `backendService` must refer to a valid `ServiceSpec.name` from `BackendSpec`.

2. **UI Constraints**:
   - View trees (`ViewNode`) must not reference `backendService` directly.
   - `EffectSpec` must only appear attached to **impure** actions.

3. **Navigation**:
   - Only allowed via `EffectSpec.kind = "navigate"`.
   - Views cannot directly manipulate routes; they must dispatch actions that trigger navigation effects.

4. **Logging/Telemetry**:
   - Only allowed via `EffectSpec.kind = "log" | "toast"`.
   - Keeps side-effects explicit and auditable.

---

## 5. Backend Independence

To ensure the backend layer remains UI-agnostic:

### 5.1 BackendSpec Restrictions

- `BackendSpec` shall not:
  - reference UI components, workspaces, or view nodes.
  - include presentation-specific fields such as labels, icons, or layout hints (these belong in UISpec or a shared i18n/metadata layer).

- `ServiceSpec` and `EndpointSpec`:
  - focus on domain operations and transport mapping.
  - should not embed UI-specific concerns (e.g. “this is for the dashboard”).

### 5.2 Service Access from UI

- UISpec must only refer to services indirectly via:
  - `EffectSpec.kind = "fetch"` and `backendService`.
- Direct references to `EndpointSpec` (HTTP path/method) are disallowed from UISpec.

---

## 6. Binding Rules by Context

We refine `Binding` usage to encode separation in the DSL.

```ts
type Binding =
  | { kind: "literal"; value: any }
  | { kind: "prop"; path: string }
  | { kind: "state"; path: string }
  | { kind: "workspaceState"; path: string }
  | { kind: "appState"; path: string }
  | { kind: "derived"; expr: string };
```

### 6.1 Binding Constraints

- **Presentational components**:
  - Allowed: `literal`, `prop`.
  - Disallowed: `state`, `workspaceState`, `appState`, `derived` (unless derived purely from props).

- **Controller components**:
  - Allowed: `literal`, `prop`, `state`, `workspaceState`, `appState`, `derived`.

- **Page components**:
  - Same as controllers; typically bind `workspaceState` and `appState`.

The runtime and validators should enforce these constraints during spec validation.

---

## 7. Validation & Linting Rules

To make these separations actionable, we define validation rules that can be run by Dazzle tooling and/or LLM agents.

### 7.1 Component-Level Validation

For each `ComponentSpec`:

- If `role === "presentational"`:
  - `state` must be empty or undefined.
  - `actions` must be empty or undefined.
  - All `Binding` instances in `view` must be `literal` or `prop` only.

- If `role === "controller"`:
  - Allowed `state` scopes: `"local" | "workspace"`.
  - Any `EffectSpec` referenced must only appear in actions marked `kind = "impure"`.

- If `role === "page"`:
  - Component must be referenced in at least one `WorkspaceSpec`.
  - Layout primitives (e.g., `LayoutShell`) should be used rather than arbitrary deep markup where possible (soft rule, useful for linting).

### 7.2 Action-Level Validation

For each `ActionSpec`:

- If `kind === "pure"`:
  - `effect` must be undefined.
- If `kind === "impure"`:
  - `effect` may be defined but must be one of:
    - `fetch`, `navigate`, `log`, `toast`.

### 7.3 UISpec/BackendSpec Cross-Validation

- Every `EffectSpec.kind = "fetch"`:
  - `backendService` must match a `ServiceSpec.name`.
- No `ViewNode` or `ComponentSpec` may:
  - reference `EndpointSpec` paths directly.
- Backend-only metadata must not appear in UISpec.

---

## 8. LLM Guidance (Prompt-Level)

The above structure should be reflected in prompt guidance for LLM agents:

- When creating new components, default to:
  - `role: "presentational"` if it only formats data.
  - `role: "controller"` if it manages state or actions.
  - `role: "page"` only when the component is a route entry point.
- Keep business rules and domain invariants in:
  - `ServiceSpec` and behaviour layer, not in the view tree.
- Use:
  - pure actions for state-only changes,
  - impure actions with Effects for backend and navigation.

LLM tools (via MCP) can include:

- `lint_uispec_for_separation_of_concerns`
- `suggest_refactors_for_presentational_controller_split`

---

## 9. Summary

By making roles, purity, and layer boundaries explicit in the DSL:

- We enforce clean separation of concerns by construction.
- We reduce accidental coupling between UI, behaviour, and backend.
- We give LLM agents a clearer grammar to work within, lowering the risk of “spaghetti spec” and cross-layer leakage.

This complements the existing DNR specs (DNR-Spec-v1, DNR-Components-v1, DNR-Mobile-Spec-v1) and should be used as a design and validation reference when evolving the Dazzle DSL and runtimes.

End of DNR-SeparationOfConcerns-v1.
