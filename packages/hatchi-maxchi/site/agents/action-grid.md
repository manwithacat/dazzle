# Action grid (`action-grid`)

Tone-tinted CTA cards with a count badge — the dashboard's 'what needs doing' surface. Cards with a URL are anchors; the grid packs intrinsically.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="action-grid-region">
  <div class="action-grid">
    <a class="action-card" data-tone="warning" href="#">
      <div class="action-card-row"><span class="action-card-icon"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span><span class="action-card-count" data-tone-badge="warning">3</span></div>
      <span class="action-card-label">Overdue invoices</span>
    </a>
    <a class="action-card" data-tone="accent" href="#">
      <div class="action-card-row"><span class="action-card-icon"><svg class="icon" aria-hidden="true"><use href="#i-receipt"/></svg></span><span class="action-card-count" data-tone-badge="accent">12</span></div>
      <span class="action-card-label">Awaiting approval</span>
    </a>
    <div class="action-card" data-tone="neutral">
      <div class="action-card-row"><span class="action-card-icon-spacer"></span></div>
      <span class="action-card-label">Nothing else today</span>
    </div>
  </div>
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

Tone tints the card surface via data-dz-tone and the count badge via data-dz-tone-badge. A URL makes the card an <a> (whole card = the target); without one it renders a static <div>. An icon SPACER holds the row height when a card has no icon.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
