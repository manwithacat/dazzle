# Stem: overlay light-dismiss

## Claim

**Disclosure chrome** (chevron) teaches “more UI is available.”
**Light-dismiss** teaches “I can abandon without committing.”

They are not substitutes. Native `<details>` only implements *toggle the
summary* — not Esc, not outside pointer. When a surface is a **transient
overlay over the user’s task**, progressive enhancement should add:

| Path | Keyboard | Touch / pointer |
|------|----------|-----------------|
| Abandon | **Escape** closes open panel(s) | **pointerdown outside** the open root |
| Commit | Activate an item / link | Same |
| Open | Summary / trigger | Tap trigger |

When a surface is **in-flow document structure** (accordion FAQ, tree), do
**not** light-dismiss: expanding is reading, not a popover layer.

## Taxonomy

| Class | Examples | Light-dismiss? | Why |
|-------|----------|----------------|-----|
| Modal / focus trap | `dialog`, `command` | **Yes** (+ explicit close for touch) | Focus captured; Esc is abort |
| Exclusive chrome strip | `menubar`, `navigation-menu` | **Yes** | OS-menu / nav mega genre; multi-peer open is wrong |
| Single overlay disclosure | `menu`, `popover` | **Yes** | Ephemeral panel over work |
| In-flow structure | `accordion`, `tree` | **No** | Structure, not a layer |

## Reconstruct

1. Is this a **layer over the task** or **document structure**?
2. Layer → implement Esc + outside (and close control if modal/touch-critical).
3. Structure → toggle trigger only; Esc closing a FAQ is surprising.
4. Touch never has Esc → outside pointer (or visible close) is mandatory for layers.
5. Disclosure chevron still required for discoverability of *open* — dismiss is separate.

## Expressions

- Controllers: `dz-menubar.js`, `dz-navigation-menu.js`, `dz-details-light-dismiss.js`
  (menu + popover), `dz-command.js` / native `<dialog>`
- Guidance on those Hyperparts; pick-a-surface note for menu family
- Pins: behaviour tests for Esc + outside on menu / popover / menubar

## Not this

- Assuming native `<details>` light-dismisses (it does not).
- Esc-only policy (fails touch).
- Light-dismiss on accordion/tree “for consistency.”
- Replacing disclosure chrome with “users will find Esc.”
