# Marker (`marker`)

Map pin chrome + optional label — host owns map projection / placement.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row" style="gap:2rem;align-items:flex-end;padding:1.5rem;background:var(--colour-surface-muted);border-radius:var(--radius-md)">
  <span class="marker" data-marker><span class="marker__pin" aria-hidden="true"></span><span class="marker__label">HQ</span></span>
  <span class="marker" data-marker data-tone="success" data-size="lg"><span class="marker__pin" aria-hidden="true"></span><span class="marker__label">Depot</span></span>
  <span class="marker" data-marker data-tone="danger"><span class="marker__pin" aria-hidden="true"></span><span class="marker__label">Alert</span></span>
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

PLACEHOLDER — shadcn parity (HMC-043). No map SDK. Position with host CSS (absolute over a map/plan). Tones via data-dz-tone.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
