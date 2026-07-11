# Queue (`queue`)

The worklist: a count, roll-up metrics, and attention-flagged rows — the triage surface for SLA-driven work.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

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

## Notes

Attention rows carry data-dz-attn="<level>" plus a human message (dz-queue-row-attn) — the flag is never colour-only. Counts and metrics are SERVER-rendered rollups (the same query that produced the rows, so they can't disagree).
