# Icon (`icon`)

Inline SVG from a vendored Lucide registry — currentColor, decorative by default. Shown here as the sprite <use> form (one sheet per page).

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="icon-demo"><svg class="icon icon--size-xs" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-md" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-lg" aria-hidden="true"><use href="#i-circle-check"/></svg><svg class="icon icon--size-xl" aria-hidden="true"><use href="#i-circle-check"/></svg></div>
```

## Guidance (prose; HTML from the registry notes field)

Two delivery forms, one registry. <strong>Sprite</strong> (<code>&lt;svg class="icon"&gt;&lt;use href="#name"/&gt;&lt;/svg&gt;</code>) is short and legible but needs the icon sheet inlined once per page — use it when an icon repeats. <strong>Inline</strong> (the full <code>&lt;svg&gt;</code> with path data) is self-contained — use it when you want no sheet dependency. Both inherit text colour via <code>currentColor</code> and are <code>aria-hidden</code> by default; pass a label for a meaningful, non-decorative icon. Sizes: <code>icon--size-xs</code> … <code>icon--size-xl</code>.
