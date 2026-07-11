# Sidebar (`sidebar-layout`)

Two panes: a fixed-ish side and a fluid content pane that wraps UNDER the side when it would get too narrow — responsive without a media query.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="sidebar-layout" style="--sidebar-width: 12rem">
  <div class="hm-demo-box">Side (12rem)</div>
  <div class="hm-demo-box">Content — wraps under the side when narrower than its minimum comfortable width.</div>
</div>
```

## Notes

The Every-Layout sidebar: flex + wrap; the side gets flex-basis: var(--dz-sidebar-width) (a PUBLIC knob — set it inline or at :root), the content gets flex-grow: 999 with min-inline-size: var(--dz-sidebar-content-min, 50%) — when the content can't hold that minimum on the line, it wraps to a full-width row. data-dz-side="end" puts the side after the content. No media query: the breakpoint is the CONTENT'S minimum, so the same markup works in a page, a card, or a drawer.
