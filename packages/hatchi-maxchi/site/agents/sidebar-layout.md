# Sidebar (`sidebar-layout`)

Two panes: a fixed-ish side and a fluid content pane that wraps UNDER the side when it would get too narrow — responsive without a media query.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="sidebar-layout" style="--sidebar-width: 12rem">
  <div class="hm-demo-box">Side (12rem)</div>
  <div class="hm-demo-box">Content — wraps under the side when narrower than its minimum comfortable width.</div>
</div>
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

The Every-Layout sidebar: flex + wrap; the side gets flex-basis: var(--dz-sidebar-width) (a PUBLIC knob — set it inline or at :root), the content gets flex-grow: 999 with min-inline-size: var(--dz-sidebar-content-min, 50%) — when the content can't hold that minimum on the line, it wraps to a full-width row. data-dz-side="end" puts the side after the content. No media query: the breakpoint is the CONTENT'S minimum, so the same markup works in a page, a card, or a drawer.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
