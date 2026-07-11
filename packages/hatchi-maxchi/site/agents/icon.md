# Icon (`icon`)

Inline SVG from a vendored Lucide registry — currentColor, decorative by default. Shown here as the sprite <use> form (one sheet per page).

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="icon-demo"><svg class="icon icon--size-xs" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-md" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-lg" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-xl" aria-hidden="true"><use href="#i-circle-check"/></svg></div>
```

## Notes

Two delivery forms, one registry. Sprite (<svg class="icon"><use href="#name"/></svg>) is short and legible but needs the icon sheet inlined once per page — use it when an icon repeats. Inline (the full <svg> with path data) is self-contained — use it when you want no sheet dependency. Both inherit text colour via currentColor and are aria-hidden by default; pass a label for a meaningful, non-decorative icon. Sizes: icon--size-xs … icon--size-xl.
