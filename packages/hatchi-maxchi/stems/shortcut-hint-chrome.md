# Stem: shortcut hint chrome

## Claim

A keyboard shortcut shown in the UI is a **hint**, not the action and not an
icon. Agents must treat it as **secondary on two axes**:

| Axis | Meaning | House expression |
|------|---------|------------------|
| **Visually secondary** | Smaller, muted, keycap chrome — not label weight | `.dz-kbd`: mono, ~0.6875rem, muted colour, chip border |
| **Spatially secondary** | Separated from the primary label by layout role | **Adjacent** or **trailing** (below) — never flush (0 gap) |

This is **nomenclature for composition**, not a new Hyperpart family: the
unit is still `kbd` / `.dz-kbd`. The stem names **roles** so agents do not
confuse shortcut chips with disclosure icons
(`affordance-disclosure-chrome`) or strip selection
(`selection-strip-honest`).

## Taxonomy / layout roles

| Role | When | Layout rule |
|------|------|-------------|
| **Adjacent hint** | Label + shortcut on one compact control (e.g. “Open palette” + ⌘K) | Parent flex **`gap ≥ var(--space-sm)`** (~8px), or equivalent margin before the chip |
| **Trailing hint** | Row / menu / command result: label leads, shortcut at the end | Flex/grid row; **`margin-inline-start: auto`** on `.dz-kbd` (or grid `1fr auto`) |
| **Prose hint** | Docs (“Press ⌘K”) | Normal word space; still wrap glyphs in `<kbd class="dz-kbd">` |

**Ban:** label text and keycap with **0px** gap inside a flex button (looks
glued; under-signals secondary metadata).

## Reconstruct

1. Is this the **primary action** or a **keyboard accelerator**?
2. Choose layout role: adjacent (compact control) vs trailing (list row).
3. Keep visual secondary: always `.dz-kbd`, never a bare Unicode glyph or Lucide “keyboard” icon as the only hint.
4. Measure if unsure: distance from label box to kbd box ≥ ~8px, **or** kbd is trailing-aligned in the row.

## House exemplars

| Surface | Role | Expression |
|---------|------|------------|
| Command gallery opener | Adjacent | `.dz-button:has(.dz-kbd) { gap: var(--space-sm) }` |
| Command result row | Trailing | `.dz-command__item .dz-kbd { margin-inline-start: auto }` |
| `kbd` gallery row | Chip set | demo row gap; pure presentation |

## Not this

- Treating ⌘K as primary iconography (affordance-disclosure-chrome rules do not apply).
- Flush adjacency because “the chip has internal padding.”
- Putting a shortcut on every dense toolbar control (clutter).
- Client fuzzy-find instead of hx-get results for the palette itself.

## Expressions

- CSS: `components/hm-core.css` (`.dz-kbd`, command item trailing, button:has kbd gap)
- Hyperparts: `kbd`, `command` (Guidance + notes)
- Pin: `test_command_opener_kbd_is_spatially_secondary`
