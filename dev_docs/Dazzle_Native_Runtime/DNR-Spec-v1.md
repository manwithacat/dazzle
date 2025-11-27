# DNR-Spec-v1

## Project: Dazzle Native Runtimes (DNR)

### Subprojects
- **DNR-Back** – Framework-agnostic backend specification and runtime.
- **DNR-UI** – LLM-first UI specification and runtime, React-class but not React-bound.

---

## 1. Purpose & Outcomes

### 1.1 Purpose
Provide infrastructure within Dazzle’s existing domain-specific language and intermediate representation (AppSpec) to support:

1. A **framework-agnostic backend specification** (BackendSpec) that can compile into:
   - A native backend runtime (Pydantic-style models + FastAPI-style services).
   - Optional builders targeting Django/DRF later.

2. A **native LLM-first UI runtime** (UISpec + DazzleUI) that consumes a semantic UI spec directly, without requiring mapping to React as the primary front-end implementation.

### 1.2 Outcomes
- DSL → AppSpec → **BackendSpec** → DNR-Back (native backend)
- DSL → AppSpec → **UISpec** → DNR-UI (native front-end runtime)

React and Django remain optional *targets*, not core assumptions.

---

## 2. High-Level Architecture

### 2.1 Layers

1. **Dazzle DSL**
   - Human-oriented domain description for entities, relationships, roles, workflows, and conceptual workspaces.

2. **AppSpec (Intermediate Representation)**
   - Canonical machine-readable spec combining:
     - **DomainSpec**
     - **BackendSpec**
     - **UISpec**

3. **Runtimes / Builders**
   - **DNR-Back**: Native backend runtime (FastAPI-style).
   - **DNR-UI**: Native LLM-first UI runtime.
   - Optional: React builder, Django/DRF builder.

### 2.2 Principles
- **Spec-first**: All truth lives in the specs.
- **LLM-first**: Structure optimised for determinism and patchability.
- **Framework-agnostic**: Front-end and back-end frameworks are outputs.
- **Evolutionary bottleneck**: App-local vocabulary compiles back to core spec.

---

## 3. BackendSpec (DNR-Back)

### 3.1 Scope
BackendSpec describes:

- Entities, fields, relationships.
- Validators & constraints.
- Services (domain operations).
- Endpoints (HTTP/RPC mapping).
- Auth & tenancy.
- Persistence hints.

### 3.2 Core Types (v1)

#### 3.2.1 EntitySpec
```ts
type EntitySpec = {
  name: string;
  label?: string;
  fields: FieldSpec[];
  relations?: RelationSpec[];
  metadata?: Record<string, any>;
};
```

#### 3.2.2 FieldSpec
```ts
type FieldSpec = {
  name: string;
  type: ScalarType | EnumType | RefType;
  required: boolean;
  default?: any;
  validators?: ValidatorSpec[];
  indexed?: boolean;
  unique?: boolean;
};
```

#### 3.2.3 RelationSpec
```ts
type RelationSpec = {
  name: string;
  from: string;
  to: string;
  kind: "one_to_many" | "many_to_one" | "many_to_many" | "one_to_one";
  backref?: string;
  onDelete?: "restrict" | "cascade" | "nullify";
};
```

#### 3.2.4 ServiceSpec
```ts
type ServiceSpec = {
  name: string;
  inputs: SchemaSpec;
  outputs: SchemaSpec;
  domainOperation: DomainOperation;
  effects?: EffectSpec[];
  constraints?: BusinessRuleSpec[];
};
```

#### 3.2.5 EndpointSpec
```ts
type EndpointSpec = {
  name: string;
  service: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  auth?: AuthRuleSpec[];
  tenancy?: TenancyRuleSpec;
  rateLimit?: RateLimitSpec;
};
```

### 3.3 DNR-Back Responsibilities
- Convert EntitySpec → Pydantic models.
- Convert ServiceSpec → domain logic stubs.
- Convert EndpointSpec → FastAPI-style routes.
- Auto-generate OpenAPI.
- Optionally map to SQLAlchemy models.
- Auth/tenancy enforcement per spec.

---

## 4. UISpec (DNR-UI)

### 4.1 Scope
UISpec describes:

- Workspaces (semantic pages/layouts).
- Components & props schemas.
- View trees (rendering structure).
- State (local/workspace/app/session).
- Actions & side-effects.
- Themes & variants.

UISpec is **not**:
- A general-purpose programming language.
- Pixel-perfect layout instructions.
- An extension of JSX.

### 4.2 Core Types (v1)

#### 4.2.1 WorkspaceSpec
```ts
type WorkspaceSpec = {
  name: string;
  persona?: string;
  layout: LayoutSpec;
  routes: RouteSpec[];
  state?: StateSpec[];
};
```

#### 4.2.2 LayoutSpec
```ts
type LayoutSpec =
  | { kind: "singleColumn"; main: string }
  | { kind: "twoColumnWithHeader"; main: string; secondary: string; header: string }
  | { kind: "appShell"; sidebar: string; main: string; header?: string };
```

#### 4.2.3 ComponentSpec
```ts
type ComponentSpec = {
  kind: "component";
  name: string;
  propsSchema: SchemaSpec;
  view: ViewNode;
  state?: StateSpec[];
  actions?: ActionSpec[];
  metadata?: Record<string, any>;
};
```

#### 4.2.4 ViewNode
```ts
type ViewNode =
  | ElementNode
  | ConditionalNode
  | LoopNode
  | SlotNode;

type ElementNode = {
  kind: "element";
  as: string;
  props?: Record<string, Binding>;
  children?: ViewNode[];
};
```

#### 4.2.5 Binding
```ts
type Binding =
  | { kind: "literal"; value: any }
  | { kind: "prop"; path: string }
  | { kind: "state"; path: string }
  | { kind: "workspaceState"; path: string }
  | { kind: "appState"; path: string }
  | { kind: "derived"; expr: string };
```

#### 4.2.6 StateSpec
```ts
type StateScope = "local" | "workspace" | "app" | "session";

type StateSpec = {
  name: string;
  scope: StateScope;
  initial: any;
  persistent?: boolean;
};
```

#### 4.2.7 ActionSpec & EffectSpec
```ts
type ActionSpec = {
  name: string;
  inputs?: SchemaSpec;
  transitions?: TransitionSpec[];
  effect?: EffectSpec;
};
```

```ts
type TransitionSpec = {
  targetState: string;
  update: PatchSpec;
};
```

```ts
type EffectSpec =
  | {
      kind: "fetch";
      backendService: string;
      onSuccess?: string;
      onError?: string;
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

#### 4.2.8 ThemeSpec & Variants
```ts
type ThemeSpec = {
  name: string;
  tokens: {
    colors: Record<string, string>;
    spacing: Record<string, number>;
    radii: Record<string, number>;
    typography: Record<string, TextStyle>;
  };
  variants?: VariantSpec[];
};

type VariantSpec = {
  name: string;
  appliesTo: string;
  tokens: Partial<ThemeSpec["tokens"]>;
};
```

### 4.3 DNR-UI Responsibilities
- Parse UISpec → internal structures.
- Render components and workspaces via DOM (or pluggable renderer).
- Manage state using signals/atoms.
- Bind text/props/visibility to state/props.
- Execute Actions and Effects.
- Apply themes via tokens.

React may be used *internally*, but UISpec is not JSX.

---

## 5. Integration Flow

### 5.1 Pipeline
1. DSL → AppSpec  
2. AppSpec → BackendSpec + UISpec  
3. BackendSpec → DNR-Back (native backend)  
4. UISpec → DNR-UI (native UI runtime)

### 5.2 LLM-First Editing
LLMs modify specs via structured patches:
- Add/remove fields or components
- Extract shared UI patterns
- Refactor layouts
- Amend services or endpoints

Runtimes are never directly edited.

---

## 6. Non-goals (v1)
- Django/DRF builder implementation (design only).
- Arbitrary custom JS within UISpec.
- Pixel-perfect layout engine.
- Multi-user collaborative editing.
- Full GraphQL v1 support.

---

## 7. Implementation roadmap

### Phase 1 — Skeleton Specs + Native Backend
- Define schemas for entities, services, endpoints, components, view nodes.
- Implement DNR-Back:
  - Pydantic model generation.
  - FastAPI routes.
  - Basic DB layer (SQLAlchemy or in-memory).

### Phase 2 — Minimal DazzleUI Runtime
- UISpec parser.
- Signals-based state system.
- DOM rendering engine with primitive components.
- Actions and Effects.

### Phase 3 — Workspaces, Themes, Personas
- Layout primitives, multi-workspace navigation.
- Theme tokens + variants.
- Persona-aware UI rules.

### Phase 4 — Optional Builders
- React builder (UISpec → React).
- Django/DRF builder (BackendSpec → Django artefacts).
- Telemetry + LLM-driven refactoring support.

---

End of DNR-Spec-v1.