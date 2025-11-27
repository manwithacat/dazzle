# DNR-Mobile-Spec-v1

## Project: Dazzle Native Runtimes – Mobile Targets

This document describes the follow-on work to **Dazzle Native Runtimes (DNR)** to support **native mobile outputs** for iOS and Android using the same AppSpec / BackendSpec / UISpec.

The core idea:

- Keep **Dazzle DSL → AppSpec → BackendSpec / UISpec** as the source of truth.
- Add mobile-specific **builders** that map this spec onto native UI toolkits (e.g. SwiftUI, Jetpack Compose), without requiring the LLM to know any platform APIs.

---

## 1. Goals & Non-Goals

### 1.1 Goals

1. Enable **native mobile apps** (iOS and Android) generated from the same Dazzle specifications used for web.
2. Reuse:
   - **BackendSpec** for all API interactions.
   - **UISpec** for semantics of workspaces, components, state, and actions.
3. Introduce **form factor awareness** and **platform profiles** to adapt UI patterns (e.g. sidebar → tab bar on phones).
4. Keep the system **LLM-first** and **token-efficient**:
   - The LLM works with the same DNR component vocabulary.
   - Builders handle platform-specific translation.

### 1.2 Non-Goals (v1)

- No direct generation of arbitrary Swift/Kotlin by the LLM.
- No pixel-perfect design export from Figma or similar tools.
- No attempt to fully support every OS-level feature (push notifications, deep linking, etc.) in v1; focus is on core UI + API flows.
- No requirement that mobile and web UIs are visually identical; only that they are semantically consistent.

---

## 2. High-Level Architecture

### 2.1 Existing Dazzle Pipeline (Recap)

- DSL → AppSpec, which includes:
  - **DomainSpec**
  - **BackendSpec**
  - **UISpec**

- From DNR-Spec-v1:
  - **DNR-Back**: uses BackendSpec to generate native backend runtime.
  - **DNR-UI**: uses UISpec to render web UI.

### 2.2 Extended Pipeline with Mobile Builders

We introduce:

- **DNR-Mobile-iOS**: Swift/SwiftUI builder.
- **DNR-Mobile-Android**: Kotlin/Jetpack Compose builder.

Pipeline:

1. DSL → AppSpec (unchanged).
2. AppSpec → BackendSpec + UISpec (unchanged).
3. BackendSpec → DNR-Back (native backend runtime).
4. UISpec + BackendSpec → DNR-UI-Web (web).
5. UISpec + BackendSpec + PlatformProfile → DNR-Mobile-iOS / DNR-Mobile-Android.

Each mobile builder:

- Consumes **UISpec** (plus some mobile-specific metadata).
- Consumes **BackendSpec** to generate typed API clients.
- Emits a mobile project skeleton with:
  - screens
  - navigation
  - views
  - data flows

---

## 3. UISpec Extensions for Mobile

We extend UISpec minimally to express form-factor and platform intent without exposing platform details to the LLM.

### 3.1 Form Factors

```ts
type FormFactor = "desktop" | "tablet" | "phone";
```

### 3.2 WorkspaceSpec Extensions

Augment `WorkspaceSpec` (from DNR-Spec-v1) with optional form-factor-specific layouts.

```ts
type LayoutVariant = {
  formFactor: FormFactor;
  layout: LayoutSpec;       // same LayoutSpec as web, but may use different kind
};

type WorkspaceSpec = {
  name: string;
  persona?: string;
  layout: LayoutSpec;       // default layout (typically desktop/web)
  routes: RouteSpec[];
  state?: StateSpec[];
  layoutVariants?: LayoutVariant[];
};
```

Notes:

- If `layoutVariants` is absent, the mobile builder derives a layout from the default and platform profile.
- If a `LayoutVariant` exists for `"phone"` or `"tablet"`, mobile builders use that as the primary layout description.

### 3.3 Component Metadata for Mobile

Allow components to carry hints for mobile usage:

```ts
type ComponentSpec = {
  kind: "component";
  name: string;
  propsSchema: SchemaSpec;
  view: ViewNode;
  state?: StateSpec[];
  actions?: ActionSpec[];
  metadata?: {
    mobilePriority?: "primary" | "secondary" | "hidden";
    mobileVariantHint?: string; // e.g. "cardList", "singleColumnForm"
    [key: string]: any;
  };
};
```

Builders can use these hints to:

- Decide which components appear on smaller screens.
- Choose appropriate visual patterns (card list vs. dense table).

---

## 4. Platform Profiles

A **PlatformProfile** describes how a given platform prefers to present navigation and dense data.

```ts
type NavModel = "sidebar" | "tabs" | "stack" | "drawer";

type PlatformProfile = {
  id: string;                      // "web", "ios", "android"
  formFactors: FormFactor[];       // e.g. ["phone", "tablet"]
  defaultNavModel: NavModel;       // e.g. "tabs" for phone, "sidebar" for tablet
  supportsDataTable: boolean;      // true on web, limited on phone
  prefersCardListForDenseData: boolean;
  defaultPageTransitionStyle?: "push" | "modal";
};
```

Examples:

- `PlatformProfile` for **iOS / phone**:
  - `defaultNavModel = "tabs"`
  - `supportsDataTable = false`
  - `prefersCardListForDenseData = true`

- `PlatformProfile` for **Android / phone**:
  - `defaultNavModel = "tabs"`
  - similar constraints as iOS.

Mobile builders reference these profiles plus UISpec to decide how to render workspaces.

---

## 5. Mapping UISpec to Mobile Navigation

### 5.1 Navigation Concepts

We derive mobile nav from:

- `WorkspaceSpec.routes`
- `PlatformProfile.defaultNavModel`
- Persona/metadata if present.

Typical mapping patterns:

- **Desktop app shell (sidebar + header)** → **Tab bar (phone)** or **drawer + stack (tablet)**.
- **Multiple primary pages** → **tabs**.
- **Detail pages** → **stack navigation** pushed from list views.

### 5.2 Example Mapping Rules (Sketched)

1. If a workspace has ≤ 5 primary routes:
   - On phone:
     - Set them as **tabs**.
     - Each tab gets its own navigation stack.
2. If there are more routes:
   - On phone:
     - Use a **drawer** or overflow menu for lower-priority pages.
3. Detail routes (e.g. `"/clients/:id"`) are generally mapped as:
   - **Stack push** from the list route screen.

Builders do not require the LLM to know or encode these rules; they apply them based on spec + profile.

---

## 6. Mapping DNR Components to Mobile UI

We reuse the **DNR-Components-v1** registry. Builders implement platform-specific renderings for primitives/patterns.

### 6.1 Primitive Component Mappings (Examples)

Given the primitives in `DNR-Components-v1`:

- `Page`:
  - iOS: `View` with `NavigationStack` or `NavigationView`.
  - Android: `Scaffold` with `TopAppBar`.

- `DataTable`:
  - Phone: rendered as a `List` or `LazyColumn` of row cards; column metadata drives row layout.
  - Tablet: may use a more table-like layout if space allows.

- `Form`:
  - iOS: vertical form in `List` or `VStack` with grouped sections.
  - Android: `Column` with `TextField`, etc.

- `Modal`:
  - iOS: `sheet` or `fullScreenCover`.
  - Android: `Dialog`.

- `Drawer`:
  - iOS: a side sheet or `NavigationSplitView`-style UI on larger screens.
  - Android: `ModalNavigationDrawer`.

Patterns like `FilterableTable`, `CRUDPage`, `WizardForm` are expanded into sequences of primitive components appropriate for mobile layouts.

### 6.2 Builder-Level Mapping Tables

Each mobile builder maintains a mapping like:

```ts
type MobileComponentMapping = {
  dnrComponent: string;          // "FilterableTable"
  formFactor: FormFactor;        // "phone" | "tablet"
  platform: "ios" | "android";
  renderStrategy: string;        // internal ID for codegen logic
};
```

For example:

- `FilterableTable` + `phone` + `ios`:
  - Render as:
    - `Page` with:
      - `SearchBox` at top,
      - `FilterChips` (`FilterBar` variant),
      - `List` of cards.

These strategies are owned by the builder, not by the LLM.

---

## 7. Backend Integration on Mobile

Mobile builders use **BackendSpec** to generate API clients:

1. For each `ServiceSpec`:
   - Generate a typed client method in Swift/Kotlin.
2. For each `EndpointSpec`:
   - Configure HTTP path, method, and payload serialization.

At runtime:

- Mobile views use generated clients to:
  - load data into local state (mirroring UISpec state).
  - trigger actions/effects (e.g. save forms, update entities).

The contract between UI and backend remains:

- UISpec `EffectSpec.kind = "fetch"` with `backendService` field pointing to `ServiceSpec.name`.

Mobile builders simply wire that to the correct platform client.

---

## 8. MCP Support for Mobile-Aware Design

The existing MCP interface (see `DNR-MCP-Spec-v1`) can be extended or reused to support mobile-aware adjustments:

### 8.1 Mobile-Related Tools (Additions)

- `list_platform_profiles`
  - Returns available platforms (web, ios, android) and profile summaries.

- `suggest_mobile_layout_variants`
  - Given a `WorkspaceSpec`, suggest `layoutVariants` for `phone` and `tablet` based on best practices.

- `audit_workspace_for_mobile`
  - Analyse a workspace and flag components likely to be problematic on phone (e.g. dense DataTable with too many columns).

These tools help an LLM agent:

- Decide when to create explicit `layoutVariants`.
- Reduce complexity for small screens.
- Stay within platform norms without knowing SwiftUI/Compose.

---

## 9. Implementation Roadmap

This work assumes **DNR-Back** and **DNR-UI-Web** are functionally in place.

### Phase 1 – Spec Extensions & Profiles

- [ ] Extend `WorkspaceSpec` to support `layoutVariants`.
- [ ] Add `FormFactor` and `PlatformProfile` types.
- [ ] Add optional `metadata.mobile*` hints to `ComponentSpec`.
- [ ] Create initial `PlatformProfile`s:
  - iOS phone, iOS tablet.
  - Android phone, Android tablet.
- [ ] Add basic MCP tools:
  - `list_platform_profiles`.
  - `audit_workspace_for_mobile` (initial heuristic).

### Phase 2 – DNR-Mobile-iOS (Minimal Viable)

- [ ] Implement iOS builder that:
  - Reads AppSpec (BackendSpec + UISpec).
  - Generates:
    - Swift package / Xcode project skeleton.
    - Basic navigation (tabs + stack).
    - Views for primitive patterns:
      - `Page`, `Form`, `SearchableList`, `CRUDPage`, `WizardForm`.
  - Uses BackendSpec to:
    - generate API client layer (e.g., using URLSession or an HTTP library).
- [ ] Support:
  - authentication screen (if specified),
  - master-detail list → detail flow,
  - simple forms (create/update).

### Phase 3 – DNR-Mobile-Android (Parity with iOS)

- [ ] Implement Android builder (Compose) with parity:
  - NavHost + bottom navigation/tab bar.
  - Equivalent screens for primitive & pattern components.
- [ ] Shared codegen conventions where possible (e.g., same template engine).

### Phase 4 – Mobile Layout Optimisation & Patterns

- [ ] Enhance layout derivation from desktop to mobile:
  - Map sidebars to tabs/drawers.
  - Map DataTable to card lists where appropriate.
- [ ] Add `layoutVariants` suggestions via MCP:
  - `suggest_mobile_layout_variants` tool.
- [ ] Add more mobile-specific pattern components if needed:
  - e.g. `BottomSheetFilter`, `PullToRefreshList`.

### Phase 5 – Refinement & Telemetry (Optional)

- [ ] Instrument mobile apps to collect:
  - screen usage,
  - navigation flows,
  - error rates.
- [ ] Feed telemetry back into LLM agents for:
  - suggesting UX simplifications,
  - recommending layout changes.

---

## 10. Summary

- Mobile becomes **“just another builder”**: same AppSpec and UISpec, different render strategies.
- The LLM continues to think in terms of:
  - entities, workspaces, components, actions,
  - DNR primitives and patterns.
- Platform-specific concerns (SwiftUI vs. Compose vs. web) are encapsulated in:
  - `PlatformProfile`s,
  - mobile builders,
  - component mapping strategies.

This keeps Dazzle’s architecture clean, extensible, and aligned with a **spec-first, LLM-first** approach for both web and mobile targets.

End of DNR-Mobile-Spec-v1.
