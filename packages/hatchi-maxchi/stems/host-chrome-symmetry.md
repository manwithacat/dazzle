# Stem: Host chrome symmetry

## Claim

L2 overlay hosts (**drawer**, **dialog**) expose a stable **chrome shell**:
`__header` / `__body` / `__footer`. The body is a **composition host** — nested
L1 Hyperparts must keep their **standalone DOM contracts**. Form scope may
differ (`form_shell` vs `exchange_shell`), but chrome BEM parts and flex
stacking stay the same. Asymmetry of *forms* is allowed; asymmetry of *chrome
shape* or *guest forks* is not.

## Reconstruct

### Chrome shells

| Shell | When | Form scope |
|-------|------|------------|
| **form_shell** | Body is authoring-time content with **no nested `<form>`** | One outer `<form method="dialog">` wraps header/body/footer (`display:contents` on the form so flex children still stack) |
| **exchange_shell** | Body is an HTMX target (may later contain forms) | Scoped `method="dialog"` forms only on close/footer actions — never wrap the live body |

Both shells:

1. Keep `dz-drawer__header|body|footer` (or dialog equivalents) as the flex column.
2. Prefer `div` chrome parts (element name is not the contract — class is).
3. Share open protocol: `data-dz-dialog-open` + native `<dialog>` close.

### Composition host

- **Body text colour is primary** — do not set `__body { color: muted }` or guests
  inherit washed-out labels/values vs their gallery demos.
- Mount the **child’s** markup (field triad, `label.switch` + track, toggle-group
  without legend *inside* the fieldset, one KPI card per metric).
- Refuse almost-DOM: `input.switch` (controls pill) ≠ Switch Hyperpart;
  `form-field` + hint without control ≠ Field; legend-in-toggle-group ≠ Toggle group.

### Peek vs full page vs widen

Three jobs; do not collapse them into one button:

| Job | Affordance | Exchange / navigation |
|-----|------------|------------------------|
| **Peek** | Open record (drawer) | `GET …?peek=1` fragment → `drawer__body` + `showModal` |
| **Full page** | **Open full page** (`<a href>`) | `GET /records/{id}` document — owned URL (gallery: Blueprint `record-page`) |
| **Widen** | **Widen** (`data-dz-drawer-widen`) | Same dialog; cycle `data-dz-width` md→lg→xl→full |

- Full page is **addressing** (new history entry, share/refresh/Back).
- Widen is **chrome** (same URL, more panel width).
- Never label a width cycle “Open full page”; never ship that label on `type=button` with no `href`.

Product peers: Linear/Jira/GitHub project panels use peek → issue route; Notion uses
peek mode → full page of the same object. Component kits (Radix/shadcn) only own
the sheet; the app owns the route.

### Machine expression

`tools/composition_matrix.py` — host × guest matrix, **declared incompatibilities
with reasons**, gallery drawer pins, Playwright coherence subset.

```bash
python packages/hatchi-maxchi/tools/composition_matrix.py --validate
python packages/hatchi-maxchi/tools/composition_matrix.py --incompatible
python packages/hatchi-maxchi/tools/composition_matrix.py --write-catalog
```

Catalog: `COMPOSITION_MATRIX.md` (generated). Guests include field, switch,
controls, toggle-group, badge, card, alert, button, menu, tabs, separator,
empty-state, popover, kbd, skeleton — plus refusal probes (`nested-form`,
`nested-dialog`, `command`).

| Compatible | Incompatible (examples) |
|------------|-------------------------|
| form_shell × field/switch/tabs/menu/… | form_shell × nested-form (invalid nested form) |
| exchange_shell × nested-form | any shell × nested-dialog / command (overlay-in-overlay) |

## Not this

- Mixing half-patterns (e.g. `<header>` only on one demo, whole-form wrap on the
  other) without a form-scope reason.
- Painting the body muted so “chrome feels soft” and breaking nested Hyperparts.
- One card wrapping three metric cells with `font-size` overrides.
- Read-only meta built as Field (label + hint, no control).
- Dogfooding `input.dz-switch` while declaring `composes` → `switch`.
- Nesting a dialog/command palette inside a drawer body “for convenience.”
- Calling a width maximize “Open full page.”
- Dead `type=button` primary labeled Open full page.

## Expressions

- Drawer / dialog gallery partials (`site/registry.py`)
- Blueprint `record-page` (full-page peer of drawer peek)
- `tools/composition_matrix.py` · `COMPOSITION_MATRIX.md`
- `tests/test_composition_matrix.py` · `tests/test_composition_matrix_playwright.py`
- `docs/agent/compose-or-refuse.md` (host mount rules)
- Related: `stems/composition-declared.md`, `stems/chrome-vs-protocol.md`
