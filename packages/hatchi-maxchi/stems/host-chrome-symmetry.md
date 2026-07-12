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

### Machine expression

`tools/composition_matrix.py` — host × guest matrix + gallery drawer pins.

```bash
python packages/hatchi-maxchi/tools/composition_matrix.py --validate
```

## Not this

- Mixing half-patterns (e.g. `<header>` only on one demo, whole-form wrap on the
  other) without a form-scope reason.
- Painting the body muted so “chrome feels soft” and breaking nested Hyperparts.
- One card wrapping three metric cells with `font-size` overrides.
- Read-only meta built as Field (label + hint, no control).
- Dogfooding `input.dz-switch` while declaring `composes` → `switch`.

## Expressions

- Drawer / dialog gallery partials (`site/registry.py`)
- `tools/composition_matrix.py`
- `docs/agent/compose-or-refuse.md` (host mount rules)
- Related: `stems/composition-declared.md`, `stems/chrome-vs-protocol.md`
