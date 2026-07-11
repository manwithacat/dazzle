# Skeleton (`skeleton`)

Loading placeholder with a lifecycle-driven sheen (TASTE-9) — drop it into a swap target while the request is in flight.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="card card-body hm-measure hm-stack" aria-hidden="true">
  <div class="hm-demo-row">
    <div class="skeleton" data-shape="circle"></div>
    <div class="hm-grow hm-stack">
      <div class="skeleton" data-shape="text"></div>
      <div class="skeleton" data-shape="text"></div>
    </div>
  </div>
  <div class="skeleton" data-shape="block"></div>
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

Purely decorative, so the placeholder region is aria-hidden; announce “loading” on the live region that owns the swap. Shapes: data-dz-shape="text|circle|block". The sheen honours prefers-reduced-motion.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
