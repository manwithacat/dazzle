# Icon (`icon`)

Inline SVG from a vendored Lucide registry — currentColor, decorative by default. Shown here as the sprite <use> form (one sheet per page).

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="icon-demo"><svg class="icon icon--size-xs" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-md" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-lg" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-xl" aria-hidden="true"><use href="#i-circle-check"/></svg></div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Two delivery forms, one registry. Sprite (<svg class="icon"><use href="#name"/></svg>) is short and legible but needs the icon sheet inlined once per page — use it when an icon repeats. Inline (the full <svg> with path data) is self-contained — use it when you want no sheet dependency. Both inherit text colour via currentColor and are aria-hidden by default; pass a label for a meaningful, non-decorative icon. Sizes: icon--size-xs … icon--size-xl.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
