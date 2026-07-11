# Center (`center`)

A measure-capped, centred column — reading width for prose and forms.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="center" data-measure="prose">
  <p class="hm-demo-muted">A comfortable reading measure tops out around 65 characters; this block centres itself and caps its width so lines stay scannable on any screen.</p>
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

margin-inline: auto + max-inline-size. data-dz-measure: prose (65ch), wide (90ch), full (no cap, still a centring context). This is the published form of the measure the gallery's own chrome uses.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
