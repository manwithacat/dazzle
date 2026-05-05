# Typed Fragment Emitter — Design

> **Status:** Approved for implementation planning
> **Author:** James Cyfuture / Claude (brainstorming session 2026-05-05)
> **Last reviewed:** 2026-05-05
> **Related ADRs:** [0004](../../adr/0004-dsl-agent-first.md), [0006](../../adr/0006-frozen-ir.md), [0011](../../adr/0011-ssr-htmx.md), [0019](../../adr/ADR-0019-surface-triple-as-atomic-unit.md), [0022](../../adr/0022-alpine-bindings-vs-idiomorph.md)
> **Related docs:** [docs/philosophy.md](../../philosophy.md)

---

## Thesis

Dazzle's Jinja templates today operate as a *compiler* from IR to HTML — they are parameterised projections of the IR rather than unique design decisions. The current substrate (Jinja + post-render contract scanner) accepts that compilation is type-poor and compensates with a 713-line scanner that detects structural violations after they happen. Replacing the substrate with a typed Fragment system makes most of those structural violations *unrepresentable* by construction. The terminal success criterion is the deletion of `src/dazzle/testing/ux/contract_checker.py`.

The change is reframed as a **renderer registry with multiple plug-in renderers**, of which Fragment is one and Jinja is another. This admits Penny Dreadful's cytoscape 3D renderer, future PDF/native targets, and per-region migration on the same surface. It is not "Fragment replaces Jinja" — it is "renderer choice becomes part of the IR, with structural correctness lifted into types where the renderer supports it."

---

## Part 1 — System Design

### 1. Fragment type catalogue

A `Fragment` is a frozen dataclass tree. The base type is the discriminated union of all primitive types:

```python
Fragment = (
    # Layout
    Stack | Row | Split | Grid
    # Containers
    | Surface | Card | Region | Toolbar | Drawer | Modal | Tabs
    # Content
    | Text | Heading | Icon | Badge | EmptyState | Skeleton
    # Interactive
    | Button | Link | InlineEdit
    # Data
    | Table | KanbanBoard | CalendarGrid | Timeline | KPI | BarChart | PivotTable
    # Forms
    | FormStack | Field | Combobox | Submit
    # Escape hatches
    | RawHTML | Slot
)
```

Each primitive is a `@dataclass(frozen=True, slots=True)` with typed fields and a `__post_init__` that encodes structural invariants. Every invariant currently scanned by `contract_checker.py` maps to either an invariant in `__post_init__` or a structural type constraint that makes the violation impossible to construct.

Three structural rules pinned in the catalogue:
- **Containment.** A `Card` cannot directly contain another `Card` (replaces `find_nested_chromes`). A `Region` has no `title` slot at the type level (replaces `find_duplicate_titles_in_cards`).
- **Primary-action visibility.** A `Toolbar.actions: tuple[Button, ...]` enforces that the first button cannot be `visibility="hidden"` (replaces `find_hidden_primary_actions`).
- **Slot exhaustion.** `Surface` has fixed slots (`header`, `body`, `footer`); the renderer cannot emit a slot the type does not declare.

The catalogue is sized at roughly **40 framework primitives**, mapping ~1:1 to the existing `~/.claude/skills/ux-architect/components/*.md` catalogue (~80 entries) after merging variants (one `Region` with `kind: list | detail | dashboard` covers six ux-architect components; one `Field` with widget variants covers the ten `widget-*` components).

### 2. Why frozen dataclasses, not Pydantic

Pydantic is being used in Dazzle for two different jobs: **boundary validation** (parsing untrusted text into typed structures) and **internal type carriers** (data flowing between trusted code paths). Fragment trees are unambiguously the second — they are constructed by typed Python code, never parsed from external input. Frozen dataclasses with `__post_init__` give the same impossibility-by-construction at a fraction of the per-node cost, which matters because Fragment trees can run to hundreds of nodes per page.

This is consistent with the principle behind Pydantic-everywhere, not a deviation from it. A one-line policy in `CLAUDE.md` and `docs/philosophy.md` makes the boundary explicit:

> Pydantic for boundary validation (parsing untrusted input). Frozen dataclasses for internal trees (constructed by typed code).

`pydantic.dataclasses.dataclass` is acknowledged as a middle option if `model_dump()` ergonomics later become needed for fragment-snapshot caching. Plain `@dataclass(frozen=True, slots=True)` is the starting point.

### 3. Renderer dispatch and the `render:` DSL clause

A new optional clause is added to surface and region blocks in the DSL grammar:

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: fragment

surface ops_dashboard:
  mode: dashboard
  render: fragment
  region citation_graph:
    render: cytoscape_3d
```

The IR gains two new fields: `SurfaceSpec.render: str | None` and `RegionSpec.render: str | None`. Linker validation checks that any named renderer is registered.

The dispatcher resolves render targets in priority order:
1. Explicit `render: <name>` in DSL → use that registered renderer.
2. App-registered preference (e.g., "all `mode: kanban` use `cytoscape_3d`").
3. Framework default for the surface mode (Fragment if a primitive exists, else Jinja).
4. `Jinja` as terminal fallback.

Renderers register at startup via `RuntimeServices.renderer_registry`:

```python
runtime.renderer_registry.register(
    name="fragment",
    handler=FragmentRenderer(primitive_registry=runtime.primitive_registry),
    supports=lambda spec: spec.mode in {"list", "detail", "form", ...},
)
```

This is the same registration pattern as FastAPI dependencies and pytest plugins — known and well-loved, no new mental model.

### 4. Per-region splice and Jinja interop

Both renderers produce HTML strings. The dispatcher walks the IR top-down and at each surface/region/fragment node selects a renderer. Output is concatenated.

**Splice helpers:**

```python
# Inside a Jinja template
{{ render_region(region_ir, ctx) }}     # dispatches to the right renderer

# Inside a Fragment tree
RawHTML(jinja_render(template_path, **ctx_dict))   # explicit drop into Jinja
```

The `RawHTML` primitive is the audit-visible trapdoor. Linting can count `RawHTML(jinja_render(...))` occurrences per surface as a migration-progress metric. When the count is zero across an example app, that app is fully Fragment-native.

**Shared contracts both renderers must honour:**
- **ID derivation** via `dazzle.render.ids.id_for(ir_node)` — never inline string literals.
- **Class derivation** via `dazzle.render.classes.classes_for(ir_node, tokens)` — single source of truth for class names.
- **htmx semantics** — both renderers emit identical htmx attributes for equivalent IR; the Jinja side via macros, the Fragment side via typed fields routed through the same emit-helper.
- **ADR-0022 compliance** — Alpine bindings are forbidden on idiomorph-morphed elements; the rule lives in the shared layer, not in each renderer.

A new policy gate (`tests/unit/test_no_inline_classes.py`) enforces that render code does not contain hardcoded class string literals, joining the existing policy-gate list.

### 5. Primitive registration API

Framework primitives are fixed at module load. App-local primitives extend via decorator-based registration:

```python
# In Aegismark's app/ui/primitives.py
from dazzle.render.fragment import primitive, Fragment, RenderContext

@primitive(name="aegismark_kanban_board")
@dataclass(frozen=True, slots=True)
class AegismarkKanbanBoard:
    columns: tuple[KanbanColumn, ...]
    swimlanes: tuple[Swimlane, ...] = ()
    tokens: Tokens | None = None

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("Kanban board needs at least one column")

    def render(self, ctx: RenderContext) -> str:
        return ctx.html("<div class='ak-kanban'>...</div>")
```

The registration name in the decorator is the DSL-visible name (referenced in `render: aegismark_kanban_board`). Linker validation at link time checks that any DSL-referenced primitive name resolves to a registered primitive *or* a registered renderer; otherwise the build fails before serve.

App-local primitives live by convention in `app/ui/primitives/` per the project layout convention.

The contract a registered primitive must satisfy:
- `@dataclass(frozen=True, slots=True)`.
- `def render(self, ctx: RenderContext) -> str`.
- Structural invariants in `__post_init__`.
- Optional `tokens: Tokens | None` for theme integration.

### 6. Token integration

Tokens are a frozen dataclass tree mirroring the primitive library: each primitive that needs theming has a corresponding `*Tokens` type.

```python
@dataclass(frozen=True, slots=True)
class CardTokens:
    radius: Literal["none", "sm", "md", "lg"] = "md"
    border: Literal["none", "subtle", "emphatic"] = "subtle"
    padding: Literal["compact", "normal", "comfortable"] = "normal"
    shadow: Literal["none", "low", "elevated"] = "none"

@dataclass(frozen=True, slots=True)
class Tokens:
    card: CardTokens = field(default_factory=CardTokens)
    button: ButtonTokens = field(default_factory=ButtonTokens)
    table: TableTokens = field(default_factory=TableTokens)
    palette: Palette = field(default_factory=Palette)
    spacing: Spacing = field(default_factory=Spacing)
```

Tokens flow via `RenderContext`, not as constructor args on every primitive. Per-instance overrides remain possible via `Card(tokens=CardTokens(radius="lg"), ...)`.

Token sheets are loaded by name. The `ux-architect` skill's `tokens/linear.md` becomes one of several seed sheets. Apps select via DSL:

```dsl
app aegismark "Aegismark":
  theme: linear
```

App-local token overrides land in `app/ui/tokens.py` returning a `Tokens` dataclass.

### 7. htmx integration

htmx attributes are typed fields on naturally-interactive primitives (`Button`, `Link`, `Form`, `InlineEdit`, `Combobox`):

```python
@dataclass(frozen=True, slots=True)
class Button:
    label: str
    variant: Literal["primary", "secondary", "danger", "ghost"] = "secondary"

    hx_get: URL | None = None
    hx_post: URL | None = None
    hx_target: TargetSelector | None = None
    hx_swap: Literal["innerHTML", "outerHTML", "beforebegin", "afterend", "delete", "none"] | None = None
    hx_trigger: HxTrigger | None = None
    hx_indicator: TargetSelector | None = None
    hx_confirm: str | None = None

    def __post_init__(self) -> None:
        if self.hx_get and self.hx_post:
            raise ValueError("Button cannot have both hx_get and hx_post")
        if any([self.hx_get, self.hx_post]) and self.hx_target is None:
            raise ValueError("htmx-bound button needs hx_target")
```

`URL` and `TargetSelector` are thin wrapper types that validate on construction. A `TargetSelector` is computed by `id_for(ir_node)`, not pasted as a string.

For interactive-on-non-interactive cases (clickable card, hover-loaded row), an `Interactive(child=...)` wrapper primitive provides the same htmx fields. Used sparingly.

**htmx fields do not propagate down the tree.** A `Card(body=Button(hx_get=...))` does not attach the htmx attrs to the card; they belong to the button alone. This rules out a class of bugs where attrs accidentally apply to the wrong element after a swap.

The post-init validators encode the htmx-correctness rules currently guarded by `test_htmx_undefined_guards`, `test_htmx_preload_silence`, and `test_preload_extension_disabled` — these become impossibilities-by-construction.

### 8. The "anti-Turing boundary"

This design extends Dazzle's existing non-Turing-complete validation surface. The IR is frozen Pydantic; predicate algebra is finite; scope is statically validated. Fragment construction sits inside the same boundary: the type system, plus `__post_init__` invariants, plus mypy, with no Turing-complete computation in the validation path. This is a coherent extension, not a new paradigm.

---

## Part 2 — Migration Strategy

### 9. Phase plan

Ten phases, each independently shippable, each with its own pre-conditions and stop conditions.

| # | Phase | Output | Stop condition |
|---|---|---|---|
| 0 | Foundations | `dazzle.render.fragment` package skeleton: `Fragment` type alias, `RenderContext`, `Tokens`, `ids.py`, `classes.py`, primitive registry, `RawHTML`, `Slot`. No primitives yet. | Module imports; no behaviour change. |
| 1 | Core primitives — leaf level | `Stack`, `Row`, `Card`, `Region`, `Toolbar`, `Text`, `Heading`, `Icon`, `Badge`, `Button`, `Link`, `EmptyState`. ~12 types. | All have `__post_init__` invariants; unit-tested via construction. |
| 2 | Structural primitives | `Surface`, `Tabs`, `Drawer`, `Modal`, `FormStack`, `Field`, `Submit`. | Construction tests pass; no renderer wiring yet. |
| 3 | First renderer | `FragmentRenderer.render(fragment) -> str`. Match-dispatch over the discriminated union. | Round-trip property test: every primitive emits valid HTML5. |
| 4 | Renderer dispatch + `render:` DSL | `render:` clause added to grammar + IR + parser + linker. `RuntimeServices` grows `renderer_registry` and `primitive_registry`. | All existing examples still serve unchanged (default = jinja). |
| 5 | First conversion target — region-level template | Smallest highest-churn template (e.g., `region_wrapper.html`) gets a Fragment equivalent. Parity test: byte-comparable HTML for the same IR. Then flip `simple_task` to use the Fragment region. | Parity test passes; **at least one scanner test retired** with no new scanner added. **Abandonment trigger:** zero scanners retired or any new scanner needed. |
| 6 | Data primitives | `Table`, `KPI`, `BarChart`, `PivotTable`, `Combobox`. Heavier work; most invariants concentrate here. | Each retires at least one scanner test on conversion. |
| 7 | Surface modes — list & detail | Convert `list_view.html` and `detail_view.html`. `simple_task` and `contact_manager` flip to surface-level `render: fragment`. | Five+ scanner tests retired cumulative; viewport e2e passes. |
| 8 | Token sheet integration | `ux-architect` linear sheet wired in as default tokens. App override mechanism shipped. | Visual diff against pre-token baseline is intentional, not accidental. |
| 9 | Form mode + remaining surfaces | All six example apps Fragment-native. | `find_nested_chromes`, `find_duplicate_titles_in_cards`, `find_hidden_primary_actions` are obsolete. |
| 10 | Scanner deletion | `src/dazzle/testing/ux/contract_checker.py` deleted. `docs/reference/card-safety-invariants.md` deleted or repurposed. `tests/unit/test_card_safety_invariants.py` deleted. | Worktree clean; success criterion satisfied. |

Phases 5 and 6 are the load-bearing experiments. Phases 7–10 happen across normal development cadence, not as a sprint.

Downstream apps (Aegismark, Penny Dreadful) can flip to `render: fragment` at any phase ≥ 5 for the surfaces the Fragment library covers.

### 10. Success and abandonment criteria

**Terminal success:** `src/dazzle/testing/ux/contract_checker.py` is deleted; all six example apps are Fragment-native (zero `RawHTML(jinja_render(...))` in rendered output); corresponding scanner tests are deleted; card-safety invariants document is deleted or repurposed.

**Per-phase abandonment triggers:**
- Phase 5: zero scanners retired after first conversion → design is wrong, revert the entire body of work (phases 0–5) and write a postmortem before considering any retry.
- Phase 6: any data primitive needs a *new* scanner because invariants cannot be expressed structurally → catalogue is wrong, redesign before continuing.
- Phase 7+: parity tests fail repeatedly because Fragment HTML diverges from Jinja in semantically meaningful ways → interop contract is broken, redesign §4.

**Indicators (tracked but not pass/fail):**
- LOC delta between Jinja template and Fragment equivalent.
- Boot time delta (Fragment construction should be cheap).
- `RawHTML(...)` occurrence count over time (monotonically decrease; growth indicates missing primitives).

### 11. Coexistence with downstream

The design intentionally supports indefinite coexistence of Jinja and Fragment renderers. Downstream apps choose per-element when to migrate. The `render:` clause defaults are picked so that:
- Surfaces with no `render:` clause pick the framework default (Fragment if available, Jinja otherwise).
- Surfaces with `render: jinja` stay on Jinja regardless of Fragment library coverage — useful when an app wants to stay frozen on the Jinja path indefinitely.
- Surfaces with `render: <custom>` use the custom renderer (Penny Dreadful's cytoscape, future PDF, etc.).

This means Phase 10 ("scanner deletion") only requires the example apps to be Fragment-native, not downstream apps. Downstream apps that have not yet migrated continue to benefit from scanner protection until Phase 10 ships. After Phase 10, the scanner is gone — downstream apps that want scanner-style protection on remaining Jinja-rendered surfaces should either complete their migration to Fragment or pin to a pre-deletion Dazzle version. This is consistent with [ADR-0003](../../adr/0003-clean-breaks.md) (no compat shims) — the scanner is not preserved as a vestigial side-channel; it goes away when its purpose is structurally subsumed.

---

## Open questions / risks

1. **Boot-time cost.** Fragment trees of hundreds of nodes per page should be cheap, but this is unmeasured. Phase 0 should include a baseline benchmark and Phase 3 should re-measure.
2. **Mypy exhaustiveness on Fragment union.** Python's `match` exhaustiveness is improving but imperfect. Need a `_fragment_exhaustiveness` test that constructs every primitive type and renders it, to catch unhandled types.
3. **Slot exhaustion vs flexibility.** `Surface(header, body, footer)` is a strong assumption. If a real surface mode genuinely needs four slots (e.g., header / sidebar / main / footer), we need a `Surface` variant or a more general `Layout` primitive. Decide on first conversion in Phase 5.
4. **Token sheet ergonomics.** The token tree could grow large. If an app wants to override one nested token (`Tokens.button.danger.hover.background`), the override syntax needs to be ergonomic. Spike this in Phase 8.

---

## Out of scope

- Replacing Jinja for sitespec marketing pages. Marketing pages are *unique design decisions*, not parameterised projections; templates remain the right tool there. ([ADR-0021](../../adr/0021-marketing-via-sitespec.md) covers sitespec.)
- Replacing the e2e contract verifier (`dazzle ux verify --contracts`). That verifier checks behaviour against AppSpec, not structural template invariants; it remains useful regardless of renderer.
- Compiling Fragments to something other than HTML. A future PDF renderer or native renderer would register as a different `Renderer` and consume the same Fragment tree, but designing that renderer is out of scope for this spec.
- Replacing Alpine.js. Client-side interactivity beyond what htmx provides remains Alpine; the rules in [ADR-0022](../../adr/0022-alpine-bindings-vs-idiomorph.md) continue to apply.

---

## Cross-references for the writing-plans pass

- DSL grammar additions: `docs/reference/grammar.md` § "render clause" (new subsection).
- IR additions: `src/dazzle/core/ir/surface.py`, `src/dazzle/core/ir/region.py`.
- Parser additions: `src/dazzle/core/dsl_parser_impl/surface.py`.
- New package: `src/dazzle/render/fragment/`.
- New runtime services: `RendererRegistry`, `PrimitiveRegistry` on `RuntimeServices`.
- Doc updates: `docs/philosophy.md` (add Pydantic-vs-dataclass policy line), `CLAUDE.md` (same).
- Skill cross-references: `~/.claude/skills/ux-architect/components/*.md` becomes prose spec for primitive types.
