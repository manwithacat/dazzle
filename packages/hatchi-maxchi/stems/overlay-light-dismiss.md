# Stem: overlay light-dismiss

## Claim

**Disclosure chrome** (chevron) teaches “more UI is available.”
**Light-dismiss** teaches “I can abandon without committing.”

They are not substitutes. Native `<details>` only implements *toggle the
summary*. Transient overlays add progressive enhancement.

Abandon has two axes (same vocabulary as shortcut secondary):

| Axis | Meaning | Typical paths |
|------|---------|----------------|
| **Spatial** | Leave the layer without re-hunting the trigger | **Escape**, **pointer outside** |
| **Temporal** | System ends the layer without another deliberate close | **timeout** (ms), hover-end (tooltip/hover-card — CSS, not this controller) |

**Default for click overlays (`menu`, `popover`):** spatial only (`esc` +
`outside`). **Temporal (timeout) is opt-in per instance** — never the default
for content that can host filters/forms.

## Per-instance configuration (lightweight)

On the openable root (`details.dz-menu`, `details.dz-popover`, …):

| Attribute | Role |
|-----------|------|
| `data-dz-dismiss` | Space-separated tokens: `esc`, `outside`, `timeout`, or `none` |
| `data-dz-dismiss-ms` | Temporal duration in ms; if set (&gt;0), enables timeout |

Examples:

```html
<!-- default (class-based): esc + outside, no timer -->
<details class="dz-popover">…</details>

<!-- explicit spatial -->
<details class="dz-popover" data-dz-dismiss="esc outside">…</details>

<!-- spatial + temporal (e.g. short preview) -->
<details class="dz-popover" data-dz-dismiss="esc outside" data-dz-dismiss-ms="4000">…</details>

<!-- timeout alone still keeps default spatial unless none -->
<details class="dz-popover" data-dz-dismiss-ms="3000">…</details>

<!-- native toggle only -->
<details class="dz-popover" data-dz-dismiss="none">…</details>
```

Controller: `controllers/dz-details-light-dismiss.js`
- **No timer when closed.** At most one `setTimeout` per open root.
- Activity **inside** an open panel **resets** the timeout (user is engaged).
- Menubar / navigation-menu keep their own exclusive controllers (same spatial
  idea, multi-peer policy).
- Accordion / tree: do **not** opt in (in-flow structure).

## Taxonomy

| Class | Examples | Spatial default | Temporal default |
|-------|----------|-----------------|------------------|
| Modal / trap | `dialog`, `command` | Esc + backdrop + close control | none |
| Exclusive strip | `menubar`, `navigation-menu` | Esc + outside | none |
| Single overlay | `menu`, `popover` | Esc + outside | **none** (opt-in ms) |
| In-flow structure | `accordion`, `tree` | none | none |
| Glance / hover | `tooltip`, `hover-card` | leave region | hover-end (CSS) |

## Reconstruct

1. Layer over the task, or document structure?
2. Layer → spatial light-dismiss (`esc` / `outside`).
3. Glance-only preview → optional `data-dz-dismiss-ms`; never default for forms.
4. Structure → no light-dismiss.
5. Touch has no Esc → `outside` is the spatial abandon path.
6. Disclosure chevron remains the **open** signal — dismiss is separate.

## Expressions

- `controllers/dz-details-light-dismiss.js` (menu + popover config)
- `dz-menubar.js` / `dz-navigation-menu.js` (strip exclusive + spatial)
- Guidance on menu / popover; pick-a-surface dismiss note
- Pins: Esc/outside defaults; timeout + `none` overrides

## Not this

- Assuming native `<details>` light-dismisses.
- Global auto-timeout on all popovers.
- Polling / interval-based dismiss (use one timeout on open only).
- Light-dismiss on accordion/tree “for consistency.”
- Esc-only without outside (fails touch).
