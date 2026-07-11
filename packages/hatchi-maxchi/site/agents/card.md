# Card (`card`)

Bordered surface with a resting stacked shadow. Content classes (label / value / delta) build KPI tiles; compose several in auto-grid so each card keeps a natural width instead of stretching full-bleed across the preview.

> **Layer:** L2 host · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="auto-grid" style="--grid-min: 11rem">
  <div class="card card-body">
    <div class="card-label">Total Revenue</div>
    <div class="card-value">£1,250.00</div>
    <div class="card-delta"><svg class="icon" aria-hidden="true"><use href="#i-trending-up"/></svg> +12.5% this month</div>
  </div>
  <div class="card card-body">
    <div class="card-label">Open invoices</div>
    <div class="card-value">18</div>
    <div class="card-delta"><svg class="icon" aria-hidden="true"><use href="#i-trending-down"/></svg> −3 vs last week</div>
  </div>
  <div class="card card-body">
    <div class="card-label">Avg. days to pay</div>
    <div class="card-value">24</div>
    <div class="card-delta"><svg class="icon" aria-hidden="true"><use href="#i-trending-up"/></svg> +2 days</div>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

This L2 host has no declared hypermedia exchanges in the registry. If you add persistent region updates, prefer `innerMorph` / `outerMorph` with stable row/panel ids; use replacement for flash panes and full resets.

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

A card is a surface, not a layout. One card in a full-width preview looks clumsy because the box stretches; real use is several cards in auto-grid (or a stack of content cards). Workspace dashboard cards add data-display for CLS height reservation — static KPI tiles omit it and size to content. Classes: dz-card + dz-card-body + dz-card-label / dz-card-value / dz-card-delta.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
