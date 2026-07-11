# Queue (`queue`)

The worklist: a count, roll-up metrics, and attention-flagged rows — the triage surface for SLA-driven work.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="queue-region hm-measure-lg">
  <div class="queue-count-row"><span class="queue-count">7</span><span>open items</span></div>
  <div class="queue-metrics">
    <div class="queue-metric">
      <div class="queue-metric-value">2</div>
      <div class="queue-metric-label">breaching today</div>
    </div>
    <div class="queue-metric">
      <div class="queue-metric-value">4h</div>
      <div class="queue-metric-label">median age</div>
    </div>
  </div>
  <ul class="queue-rows">
    <li class="queue-row" data-attn="critical">
      <div class="queue-row-main">
        <div class="queue-row-headline"><span class="queue-row-title">Refund request — Acme</span></div>
        <p class="queue-row-attn">SLA breaches at 16:00 — assign now.</p>
        <span class="queue-row-date">2h left</span>
      </div>
    </li>
    <li class="queue-row">
      <div class="queue-row-main">
        <div class="queue-row-headline"><span class="queue-row-title">KYC review — Globex</span></div>
        <span class="queue-row-date">due tomorrow</span>
      </div>
    </li>
  </ul>
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

Attention rows carry data-dz-attn="<level>" plus a human message (dz-queue-row-attn) — the flag is never colour-only. Counts and metrics are SERVER-rendered rollups (the same query that produced the rows, so they can't disagree).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
