# Progress (`progress`)

Toned determinate bar.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack hm-measure">
  <div class="progress" role="progressbar" aria-label="Storage used" aria-valuenow="62" aria-valuemin="0" aria-valuemax="100">
    <div class="progress__bar" style="--progress-value:62%"></div>
  </div>
  <div class="progress" data-tone="success" role="progressbar" aria-label="Upload progress" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100">
    <div class="progress__bar" style="--progress-value:100%"></div>
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

## Source files

- `site/registry.py` (partial + exchanges + guidance)
