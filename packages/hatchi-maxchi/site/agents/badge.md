# Badge (`badge`)

Colour + icon + text — status never relies on colour alone (WCAG 1.4.1).

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="hm-demo-row">
  <span class="badge" data-tone="success"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>Approved</span>
  <span class="badge" data-tone="warning"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>Pending</span>
  <span class="badge" data-tone="destructive"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-x"/></svg></span>Rejected</span>
  <span class="badge" data-tone="neutral">Draft</span>
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

## Source files

- `site/registry.py` (partial + exchanges + guidance)
