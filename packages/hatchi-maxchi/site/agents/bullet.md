# Bullet chart (`bullet`)

Actual vs target on qualitative bands — the KPI-with-context bar. All geometry is server-computed inline percentages.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="bullet-region hm-measure-lg">
  <div class="bullet-rows">
    <div class="bullet-row">
      <span class="bullet-label">Revenue</span>
      <div class="bullet-track"><span class="bullet-band" style="left: 0%; width: 60%; background: var(--colour-danger);" title="Poor: 0–60"></span><span class="bullet-band" style="left: 60%; width: 25%; background: hsl(40, 90%, 55%);" title="OK: 60–85"></span><span class="bullet-band" style="left: 85%; width: 15%; background: hsl(145, 55%, 45%);" title="Good: 85–100"></span><span class="bullet-actual" style="width: 72%;" title="Revenue actual: 72"></span><span class="bullet-target" style="left: 80%;" title="Revenue target: 80"></span></div>
      <span class="bullet-value">72 / 80</span>
    </div>
  </div>
  <p class="bullet-summary">1 rows · scale 0–100</p>
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

Bands, the actual bar, and the target tick are absolutely positioned by SERVER-computed inline percentages (per-row data, the same contract as the funnel widths); each carries a title with its numeric range. Band fills come from the server's reference-band colour map (target → var(--colour-brand), destructive → var(--colour-danger), plus fixed positive/warning/muted values) — saturated colours, because the band layer renders at 0.18 opacity. The value (and target, when set) renders as text beside the track; the mono summary line carries row count and scale.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
