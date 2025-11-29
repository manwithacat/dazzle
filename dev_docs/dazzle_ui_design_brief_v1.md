# Dazzle UI Runtime – LLM Coder Design Brief (v1)

## 1. Overall Objective

- Design and implement a minimal UI runtime inspired by the best parts of React’s component model (composition, props, unidirectional data flow) without importing React itself.
- Provide a styling system that:
  - Uses design tokens and CSS variables as first-class primitives.
  - Can express modern “design system” level polish (spacing, typography, colour, elevation, motion).
  - Avoids the legacy weight and cognitive overhead of Bootstrap, Tailwind, or similar large CSS frameworks.
- Optimise all APIs for LLM-first development: deterministic, small vocabulary, and strongly schema-driven.

---

## 2. Component Model (React-Inspired, Not React-Dependent)

1. Define a **pure render function model** for components:

   - Model each component as a pure function of `(props, localState, context) -> UI tree`.
   - Ensure components do not perform side effects during render.
   - Represent the UI tree as a JSON-serialisable structure, not JSX.

2. Implement a **unidirectional data flow**:

   - Ensure data flows downward via props and context.
   - Ensure events bubble upward as discrete, typed messages (e.g. `{ type: "click", target: "approve_button", payload: {...} }`).
   - Avoid bidirectional data binding and implicit mutation.

3. Define a **minimal, stable set of primitive components**:

   - Provide primitives such as `Workspace`, `Surface`, `Stack`, `Grid`, `List`, `Form`, `Field`, `ActionBar`, `Button`, `Tabs`, `Dialog`, `Toast`.
   - Implement these primitives in HTML + CSS with minimal JS for behaviour.
   - Expose behaviour as declarative properties (e.g. `layout.direction = "horizontal"`), not arbitrary JS handlers.

4. Implement a **lightweight reconciliation/patching layer**:

   - Accept a declarative UI tree from the server or from an LLM-generated spec.
   - Diff the new tree against the existing DOM-representation and patch only changed nodes.
   - Avoid a full virtual DOM complexity; implement a small, focused diff strategy tuned to the Dazzle component schema.

5. Formalise a **context mechanism**:

   - Support ambient data such as `theme`, `tenant`, `user`, `locale`, and `permissions` via a context object.
   - Ensure context is read-only during render and updated only via explicit events or server responses.

---

## 3. Event and State Model

1. Define a **constrained event system**:

   - Standardise event types: `click`, `change`, `submit`, `select`, `navigate`, `load`, `close`.
   - Represent each event as a structured object, not as inline JS functions.
   - Provide a mapping layer that routes events to declarative behaviours (e.g. `invokeServerAction`, `applyLocalTransition`, `navigateToSurface`).

2. Design **local component state** as finite state machines:

   - Represent local state as small, discrete states (e.g. dialog `open`/`closed`, tabs `activeTab` key).
   - Implement transitions as named actions (e.g. `transition("dialog", "open")`), not arbitrary mutation.
   - Ensure all allowed transitions are defined in a schema so that LLMs can reason over the permitted state changes.

3. Use a **view model per workspace**:

   - Maintain a structured view model describing the visible data, filters, selection, and sorting for a workspace.
   - Make view model updates explicit through events and transitions.
   - Ensure the view model can be serialised and used as context for server-side reasoning or LLM planning.

---

## 4. Styling System – Design Tokens and CSS Variables

1. Implement **design tokens as the foundation**:

   - Define core tokens for:
     - Colours (e.g. `color.background.default`, `color.text.muted`, `color.intent.primary`, `color.intent.danger`).
     - Typography (e.g. `font.family.base`, `font.size.sm/md/lg`, `font.weight.normal/semibold`).
     - Spacing (e.g. `space.xs/sm/md/lg/xl`).
     - Radii (e.g. `radius.sm/md/lg/full`).
     - Shadows/elevation (e.g. `shadow.sm/md/lg`).
     - Motion (e.g. `transition.fast/normal/slow`).
   - Store tokens in a JSON/YAML schema that Dazzle and LLMs can manipulate directly.

2. Compile tokens to **CSS custom properties**:

   - Generate a root-level `:root` block with CSS variables derived from the token set (e.g. `--color-bg-default`, `--space-md`).
   - Names should be stable, predictable, and easily generated from token keys.
   - Prefer semantic naming (`--color-intent-danger`) over raw palette naming (`--red-500`), but allow internal palette tokens where needed.

3. Design a **semantic styling layer** on top of tokens:

   - Map semantic roles such as `surface`, `card`, `button.primary`, `button.danger`, `input`, `label`, `chip`, `tag`, `badge`, to concrete CSS rules using the tokens.
   - Use class names that express semantic roles (e.g. `.dz-surface`, `.dz-button--primary`, `.dz-badge--info`). Avoid highly-compressed or opaque names.
   - Ensure that all important visual patterns (spacing, border radius, shadow, typography) can be expressed by combining semantic classes with the underlying token variables.

4. Avoid Bootstrap/Tailwind-style global utility sprawl:

   - Do not generate thousands of utility classes for every token combination.
   - Instead, define a **small, curated set of utilities** for layout and spacing where it significantly reduces redundancy (e.g. `.dz-flex`, `.dz-stack`, `.dz-gap-md`, `.dz-text-muted`).
   - Keep utilities consistent, documented, and stable so that LLMs can use them without ambiguity.

5. Support **theme variants and dark mode**:

   - Implement light/dark (and future theme variants) using CSS custom properties, toggled via `data-theme` attributes on `html` or `body`.
   - Ensure token resolution respects the active theme context (e.g. `--color-bg-default` resolves differently in dark mode).
   - Allow tenants to override selected tokens (e.g. primary accent colour) without changing component-level CSS rules.

---

## 5. Layout and Responsiveness

1. Use **CSS Grid and Flexbox** as primary layout mechanisms:

   - Implement `Stack` and `Grid` components using Flexbox and CSS Grid respectively.
   - Provide simple, declarative props/attributes for direction, gap, alignment, wrapping, and responsive breakpoints.
   - Map these props to semantic classes and CSS variables (e.g. `.dz-stack--vertical`, `.dz-stack--gap-md`, `.dz-grid--cols-3@md`).

2. Design a **responsive breakpoint system**:

   - Define a small, stable set of breakpoints (e.g. `sm`, `md`, `lg`, `xl`) as design tokens (e.g. `breakpoint.sm`).
   - Use these breakpoints to define responsive variants in CSS (e.g. `@media (min-width: var(--breakpoint-md)) { ... }`).
   - Ensure LLMs can express responsiveness declaratively in the UI schema (e.g. `columns: { base: 1, md: 2, lg: 3 }`).

3. Enforce **accessible and robust layout defaults**:

   - Avoid layouts that depend on fixed pixel positioning unless absolutely necessary.
   - Provide sensible defaults for padding, margin, and line length so that generated UIs are readable without manual tuning.

---

## 6. Accessibility and Interaction Quality

1. Bake **a11y into the primitives**:

   - Ensure all interactive components include keyboard navigation, focus states, ARIA attributes, and proper roles by default.
   - Implement tab order and focus management for `Dialog`, `Tabs`, and `Menu` components.
   - Provide visually distinct focus outlines and states using design tokens.

2. Standardise **interaction patterns**:

   - Define consistent behaviour for hover, focus, active, and disabled states across all button-like and link-like components.
   - Use motion and transition tokens to provide subtle but clear feedback (e.g. elevation change on hover, colour transition on state change).

3. Ensure **fallbacks when JS is unavailable**:

   - For core navigation and basic forms, ensure the HTML and CSS remain usable without JS.
   - Use data attributes and progressive enhancement so that JS only augments behaviour, not defines it.

---

## 7. Implementation Constraints and Approach

1. Minimise third-party dependencies:

   - Implement core runtime logic (render, diff, state transitions) using vanilla JavaScript or a small ES module foundation.
   - Avoid importing React, Vue, or large component libraries.
   - Use micro-libraries only when they significantly reduce complexity and are stable and well-maintained.

2. Optimise for LLM ergonomics:

   - Define all component props, event types, and style variants in machine-readable schemas (e.g. JSON Schema or TypeScript type declarations).
   - Ensure naming is consistent, descriptive, and non-ambiguous so that LLMs can reliably generate correct configuration.
   - Avoid patterns that depend on runtime closures or dynamic code generation in the browser.

3. Provide a **clear boundary between spec and runtime**:

   - Treat the UI spec (component tree + behaviour + style references) as data.
   - Treat the runtime as a deterministic engine that interprets this data and manipulates the DOM and CSS accordingly.
   - Ensure the runtime can operate with partial updates (e.g. new surface, updated view model) without needing a full re-render of the entire app.

4. Document the **component and styling contracts**:

   - Produce a concise reference for each primitive component: purpose, props, events, state, and styling hooks (classes, data attributes, CSS variables).
   - Produce a design token catalogue including example mappings to CSS custom properties and semantic classes.
   - Ensure the documentation is structured in a way that can be embedded in prompt context for LLMs.

---

## 8. Deliverables

1. A minimal but complete **UI runtime** (ES modules) implementing:
   - Component render and patching.
   - Event dispatch and state transitions.
   - Context and view model handling.

2. A **design token system**:
   - Token schema (JSON/YAML).
   - Compiler/generator that produces CSS variables and base CSS.

3. A **base component library**:
   - Core primitives implemented using semantic HTML, CSS, and minimal JS.
   - Semantic classes and CSS using design tokens.

4. **Machine-readable schemas and documentation**:
   - Type definitions / JSON Schemas for components, tokens, events, and behaviours.
   - Markdown or similar docs targeted at both human developers and LLM prompts.

Implement all of the above with a strong bias towards simplicity, determinism, and composability so that Dazzle can reliably use this runtime as the default presentation layer for LLM-generated applications.
