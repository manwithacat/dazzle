# Sidebar (`sidebar-layout`)

Two panes: a fixed-ish side and a fluid content pane that wraps UNDER the side when it would get too narrow — responsive without a media query.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="sidebar-layout" style="--sidebar-width: 12rem">
  <div class="hm-demo-box">Side (12rem)</div>
  <div class="hm-demo-box">Content — wraps under the side when narrower than its minimum comfortable width.</div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The Every-Layout sidebar: flex + wrap; the side gets <code>flex-basis: var(--dz-sidebar-width)</code> (a PUBLIC knob — set it inline or at :root), the content gets <code>flex-grow: 999</code> with <code>min-inline-size: var(--dz-sidebar-content-min, 50%)</code> — when the content can't hold that minimum on the line, it wraps to a full-width row. <code>data-dz-side="end"</code> puts the side after the content. No media query: the breakpoint is the CONTENT'S minimum, so the same markup works in a page, a card, or a drawer.
