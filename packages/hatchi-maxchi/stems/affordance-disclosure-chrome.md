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

| Stem | Affordance |
|------|------------|
| `accordion` | `::after` 1rem SVG mask; rotates when `[open]` |
| `navigation-menu` | same family on `__trigger::after` |
| `tree` | `.tree-chevron` SVG ~0.75rem; rotates 90° when open |
| `grid` / table sort | `{svg:chevron-up}` in sort button; oriented by `aria-sort` |
| `menubar` | no caret (app-menu genre); exclusive open is behavioural, not chevron |

## Not this

- Reintroducing `<span class="…__caret">▾</span>` on nav triggers.
- “Fixing” scale only by bumping Unicode `font-size` without house stroke language.
- Inventing Alpine/React for a chevron.
- Treating menubar’s lack of caret as license to drop nav submenu chrome
  (different product genre — site nav almost always signals panels).

## Expressions

- CSS: `components/accordion.css`, `components/navigation-menu.css`,
  `components/tree.css`, `components/table.css`
- Partials: no Unicode carets on `navigation-menu` triggers
- Guidance on `navigation-menu` / `accordion` agent packs
- Behaviour pin: `test_navigation_menu_disclosure_chevron_scale`
