# Stem: affordance disclosure chrome

## Claim

When a control **opens more content on interaction** (accordion panel, nav
submenu, tree branch, sortable column), the **visual affordance** must be
legible at control scale and drawn in the **house disclosure language** —
not a tiny Unicode glyph.

| Intent | Mechanism | Size floor |
|--------|-----------|------------|
| Expand / collapse peers | CSS mask chevron on trigger (`::after`) **or** Lucide stroke SVG | **≥ 0.75rem**, prefer **1rem** |
| Open state | Rotate or flip the **same** glyph (accordion 180°, tree 90°) | — |
| AT | Decorative only (`aria-hidden` / pure CSS); open state lives in DOM (`details`, `aria-expanded`, `aria-sort`) | — |

**Ban for primary chrome:** Unicode `▾` / `▲` / `▼` as the sole submenu
signal, and `font-size` **&lt; ~0.75em** of the adjacent label (optical
whisper scale).

## Reconstruct

1. Is this a **plain link** or a **disclosure trigger**?
2. If disclosure: match **accordion** (CSS chevron) or **tree/table**
   (Lucide `{svg:chevron-*}`), not a one-off glyph.
3. Size in **rem** (or fixed mask box), not `0.65em` of label type.
4. Prefer open-state **rotation** on the same chrome (not a second glyph).

## House exemplars

| Surface | Affordance |
|---------|------------|
| `accordion` | `::after` 1rem SVG mask; rotates when `[open]` |
| `navigation-menu` | same family on `__trigger::after` |
| `menu` | same family on `summary::after` (label is plain “Actions”) |
| `tree` | `.tree-chevron` SVG ~0.75rem; rotates 90° when open |
| `grid` / table sort | `{svg:chevron-up}` in sort button; oriented by `aria-sort` |
| `menubar` | no caret (app-menu genre); exclusive open is behavioural, not chevron |

**Wording:** “affordance” here means the **visual signal that more UI is
available on interaction** (expand/open). Prefer that phrase over “icon”
when the mark is decorative disclosure chrome, not a content icon
(`{icon:pencil}` on a menu *item* is content, not disclosure).

## Not this

- Reintroducing `<span class="…__caret">▾</span>` on nav triggers.
- Baking `▾` / `▼` into summary/button **label text** (e.g. `Actions ▾`).
- “Fixing” scale only by bumping Unicode `font-size` without house stroke language.
- Inventing Alpine/React for a chevron.
- Treating menubar’s lack of caret as license to drop nav/menu disclosure chrome
  (different product genres).

## Expressions

- CSS: `components/accordion.css`, `components/navigation-menu.css`,
  `components/alert.css` (`.dz-menu`), `components/tree.css`, `components/table.css`
- Partials: no Unicode carets in `menu` / `navigation-menu` trigger labels
- Guidance on those Hyperparts; optional pin: no `▾` in menu partial
- Guidance on `navigation-menu` / `accordion` agent packs
- Behaviour pin: `test_navigation_menu_disclosure_chevron_scale`
