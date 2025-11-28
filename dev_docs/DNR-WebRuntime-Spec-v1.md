# DNR-WebRuntime-Spec-v1

## Project: Dazzle Native Runtimes (DNR)
### Topic: Web Runtime for UISpec (Vite-Bundled, Framework-Free)

This document specifies the **DNR Web Runtime** (DNR-Web), responsible for rendering UISpec to the browser DOM, handling state, actions, and effects – without React or any other UI framework. Bundling is assumed to be done with **Vite**.

The runtime is designed to be:

- **Spec-first & LLM-first** – reads UISpec/ThemeSpec, not JSX/TSX.
- **Framework-free** – no React/Vue/Svelte; minimal native JS + DOM.
- **Token-efficient** – avoids leaking low-level styling into the spec.
- **Performant** – fine-grained updates, minimal DOM work.
- **Skin-aware** – uses DNR-Theming & skins (Tailwind/Bootstrap/custom CSS).

---

# 1. Inputs & Responsibilities

## 1.1 Primary Inputs

DNR-Web consumes:

- **UISpec**  
  - Workspaces, components, view trees, bindings, actions, effects.
- **ThemeSpec** (from DNR-Theming-Spec-v1)  
  - Design tokens (colors, spacing, typography, etc.).
- **Skin**  
  - Mapping from semantic variants/layout to CSS classes/inline styles.
- **BackendConfig**  
  - Base URL, auth/token strategy, tenant identification, etc.
- **InitialState** (optional)  
  - Server-provided state snapshot for hydration or SSR scenarios.

## 1.2 Responsibilities

DNR-Web must:

1. Initialise the application within a DOM root.
2. Manage state scopes:
   - local, workspace, app.
3. Render `ViewNode` trees into DOM elements.
4. Handle UI events, dispatch actions, and apply state transitions.
5. Execute effects (fetch/navigate/log/toast) and feed results back into actions.
6. Apply theming and skins to produce concrete CSS for elements.
7. Integrate with the browser:
   - routing (pushState/replaceState/popstate),
   - history,
   - basic accessibility patterns (focus management, ARIA attributes where applicable).

---

# 2. Runtime Architecture

## 2.1 Core Subsystems

1. **Spec Loader**
   - Loads UISpec, ThemeSpec, and Skin configuration.
2. **State Engine**
   - Manages signals/atoms for app, workspace, and local state.
3. **Renderer**
   - Translates `ViewNode` → DOM, using fine-grained updates.
4. **Action Dispatcher**
   - Executes `ActionSpec` (pure/impure), applies transitions.
5. **Effect Handler**
   - Executes `EffectSpec` (fetch, navigate, log, toast).
6. **Router**
   - Maps browser location → `WorkspaceSpec` + `ComponentSpec` (page).
7. **Styling Engine**
   - Resolves semantic styles → concrete classes/styles via Skin.

## 2.2 Entry Point (Vite Integration)

Assume a typical Vite project structure:

- `index.html`
- `src/main.ts` / `src/main.js`
- `src/dnr-runtime/*` (runtime code)
- `src/spec/uispec.json` (or dynamic fetch from backend)
- `src/spec/theme.json`

Example `main.ts` responsibilities:

1. Import `startDnrWebApp` from runtime.
2. Load UISpec/ThemeSpec (inline import or fetch).
3. Instantiate a Skin (e.g. TailwindSkin).
4. Call `startDnrWebApp({ rootElement, uiSpec, theme, skin, backendConfig })`.

---

# 3. UISpec Integration

## 3.1 Workspace & Route Resolution

- DNR-Web uses `WorkspaceSpec` and `RouteSpec` to determine:
  - which page component to render for a given URL path,
  - what initial workspace state should be.

Routing steps:

1. On initial load, read `window.location.pathname`.
2. Match against `RouteSpec` definitions:
   - path patterns (e.g. `/clients/:id`).
3. Determine:
   - active workspace,
   - active page component,
   - route params.

4. Render that page via the **Renderer**.

On navigation:

- `EffectSpec.kind = "navigate"` triggers the Router:
  - pushes new state using `history.pushState`,
  - updates visible page component.

## 3.2 Component Registry

DNR-Web maintains an in-memory registry:

```ts
type ComponentRegistry = Map<string, ComponentSpec>;
```

- Built from UISpec at startup.
- Used to:
  - instantiate page components,
  - nest controller/presentational components.

---

# 4. State Engine

The state engine provides a minimal signal/atom-based system.

## 4.1 State Scopes

From UISpec / DNR-SeparationOfConcerns-v1:

- `local` – component-local state.
- `workspace` – shared across components in a workspace.
- `app` – global application state.

## 4.2 Signal Abstraction

```ts
type Signal<T> = {
  get(): T;
  set(value: T): void;
  subscribe(listener: () => void): () => void;
};
```

Implementation details:

- Internally stores `value: T` and a `Set` of listeners.
- `set` updates value and notifies listeners.
- Subscriptions are used by:
  - view bindings,
  - derived computations.

## 4.3 StateSpec → Signals

DNR-Web maps each `StateSpec` to signals:

- `StateSpec.scope = "app"`:
  - Stored in a global map.
- `"workspace"`:
  - Stored in a per-workspace map.
- `"local"`:
  - Stored in a per-component instance map.

Example:

```ts
type StateStore = {
  app: Record<string, Signal<any>>;
  workspace: Record<string, Record<string, Signal<any>>>;
  local: WeakMap<ComponentInstance, Record<string, Signal<any>>>;
};
```

Where `ComponentInstance` is an internal handle representing a mounted component.

---

# 5. View Renderer

## 5.1 ViewNode Shapes

The renderer operates on `ViewNode` definitions, which may include:

- Elements:
  - `{ kind: "element", as: "Button" | "Card" | "div" | ... }`
- Text:
  - `{ kind: "text", value: string | Binding }`
- Component references:
  - `{ kind: "component", name: string, props: Record<string, Binding> }`
- Conditional:
  - `{ kind: "conditional", when: Binding, then: ViewNode[], else?: ViewNode[] }`
- Loop:
  - `{ kind: "loop", from: Binding, as: string, children: ViewNode[] }`

## 5.2 Render Algorithm (Conceptual)

1. For a given root component (page):
   - Instantiate local state signals.
   - Evaluate view tree with bindings.
   - Create DOM elements and attach event listeners.
   - Register subscriptions to relevant signals.

2. On state change:
   - Signal notifies listeners.
   - Renderer updates only the affected DOM segment.

DNR-Web should favour:

- fine-grained updates per binding or node,
- avoiding full re-render of entire subtrees where possible.

## 5.3 Binding Resolution

Bindings (from UISpec):

```ts
type Binding =
  | { kind: "literal"; value: any }
  | { kind: "prop"; path: string }
  | { kind: "state"; path: string }
  | { kind: "workspaceState"; path: string }
  | { kind: "appState"; path: string }
  | { kind: "derived"; expr: string };
```

Resolution:

- `literal`:
  - direct value.
- `prop`:
  - read from component instance props object.
- `state` / `workspaceState` / `appState`:
  - read from appropriate Signal.
- `derived`:
  - evaluate expression in a sandboxed context with props + state values.
  - Optionally tracked as a computed signal.

---

# 6. Styling & Skins

## 6.1 Applying Skins

For each element-like node:

1. Determine component type:
   - e.g., `"Button"`, `"Card"`, `"DataTable"`.
2. Read semantic style props from UISpec:
   - `variant`, `size`, `density`, `layoutKind`, etc.
3. Call Skin:

```ts
const styles = skin.mapComponentVariant("Button", variant, size, density);
```

4. Apply the resulting `ResolvedWebStyles`:
   - `cssClassList` → add classes to DOM element.
   - `inlineStyles` → assign `style` properties.
   - `cssModuleRef` → map to module class.

## 6.2 CSS Variables from ThemeSpec

At startup, DNR-Web calls:

```ts
const cssVars = skin.mapTokens(theme);
```

This returns a map of CSS variable names → values, e.g.:

```ts
{
  "--dnr-color-primary": "#4f46e5",
  "--dnr-spacing-md": "1rem",
  ...
}
```

The runtime injects these into:

- `:root` style element, or
- a dedicated theme `<style>` tag.

This supports theming without inlining values in every element.

---

# 7. Actions & Effects

## 7.1 Action Dispatch

Each interactive element (e.g., `Button`) may specify `onClick` or similar event props referencing an `ActionSpec.name`.

Runtime flow:

1. DOM event → lookup associated action name.
2. Call `dispatch(actionName, payload, context)`.

Where `context` includes:

- current state store (app/workspace/local),
- routing context,
- backend client,
- logger/toast handlers.

## 7.2 Executing ActionSpec

Recall:

```ts
type ActionSpec = {
  name: string;
  kind: "pure" | "impure";
  inputs?: SchemaSpec;
  transitions?: TransitionSpec[];
  effect?: EffectSpec;
};
```

Execution:

1. Validate payload against `inputs` (if provided).
2. Apply `transitions`:
   - update signals according to `TransitionSpec`.
3. If `kind === "impure"` and `effect` is present:
   - pass to Effect Handler.

## 7.3 Effect Handler

Supported effects:

- `fetch` – call backend service.
- `navigate` – route change.
- `log` / `toast` – UI-side messaging.

### 7.3.1 Fetch

1. Map `EffectSpec.backendService` → `ServiceSpec` (from BackendSpec).
2. Build HTTP request:
   - base URL from BackendConfig.
   - path, method, query/body from ServiceSpec.
3. Execute fetch with appropriate headers/auth.
4. On success:
   - if `onSuccess` defined, dispatch that action with response data.
5. On error:
   - if `onError` defined, dispatch error action with details.

### 7.3.2 Navigate

1. Build target URL from `route` and `params`.
2. Update browser history.
3. Re-run route resolution and re-render page.

### 7.3.3 Log / Toast

- `log`:
  - emit to console or registered logger.
- `toast`:
  - push message into an app-wide toast state and render via a toast component.

---

# 8. Router & URL Handling

## 8.1 RouteSpec Mapping

The Router uses `RouteSpec` entries from UISpec:

```ts
type RouteSpec = {
  path: string;                  // e.g. "/clients/:id"
  workspace: string;             // WorkspaceSpec.name
  pageComponent: string;         // ComponentSpec.name with role "page"
};
```

Matching:

- Use a simple path-to-regexp mechanism to extract params.
- If no match, fall back to a “not found” route (if defined).

## 8.2 Browser Integration

- On `EffectSpec.navigate`:
  - `history.pushState(state, "", url)`.
  - Trigger rerender.
- On `window.onpopstate`:
  - read location, re-resolve route, rerender.

---

# 9. Vite Bundling Model

## 9.1 Dev Mode

- Vite dev server provides:
  - fast HMR for runtime code.
  - static or dynamically fetched UISpec/ThemeSpec.
- DNR-Web should support:
  - reloading UISpec without page reload (optional, for local dev).
  - logging for actions/effects.

## 9.2 Build Mode

- Vite builds:
  - a single or limited set of bundles:
    - `main.[hash].js` for runtime + app code.
    - `theme.[hash].css` optionally for base styles/skins.
- UISpec/ThemeSpec can be:
  - embedded as static JSON imports, or
  - fetched from DNR-Back at runtime via `/api/uispec` and `/api/theme`.

## 9.3 Environment Configuration

BackendConfig can be provided via:

- Vite env variables:
  - `import.meta.env.VITE_API_BASE_URL`
- Or via a small JSON config loaded at boot:
  - `/config/dazzle-config.json`.

---

# 10. Performance Considerations

DNR-Web should:

- Avoid heavy VDOM and full-tree diffing.
- Use direct DOM updates driven by signals:
  - each binding subscribes to relevant signals.
  - on change, only the relevant text/content/attributes/styles update.
- Minimise layout thrashing:
  - batch DOM updates within a microtask or animation frame.
- Allow tree-shaking of unused components/skins:
  - depend on Vite/Rollup to prune unused imports.

---

# 11. Error Handling & Dev Tools

## 11.1 Runtime Errors

- Catch and log:
  - missing components,
  - unresolved bindings,
  - invalid action names.
- Optionally render a “runtime error overlay” in dev mode.

## 11.2 Debug Hooks

Exposed hooks (for possible dev tools):

- Inspect current app/workspace/local state.
- Inspect last dispatched actions and effects.
- Toggle a “debug mode” overlay showing component boundaries and bindings.

---

# 12. Summary

DNR-WebRuntime:

- Is a **framework-free**, Vite-bundled JavaScript runtime.
- Reads **UISpec + ThemeSpec + BackendSpec** and a **Skin**.
- Manages signals, views, actions, and effects.
- Renders to DOM with fine-grained updates.
- Uses Tailwind/Bootstrap/custom CSS **only via skins**, never in the spec.
- Fits seamlessly into the broader Dazzle Native Runtime ecosystem and supports future mobile/native builders.

End of DNR-WebRuntime-Spec-v1.
