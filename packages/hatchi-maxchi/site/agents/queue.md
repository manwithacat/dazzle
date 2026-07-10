# Queue (`queue`)

The worklist: a count, roll-up metrics, and attention-flagged rows — the triage surface for SLA-driven work.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

Attention rows carry <code>data-dz-attn=&quot;&lt;level&gt;&quot;</code> plus a human message (<code>dz-queue-row-attn</code>) — the flag is never colour-only. Counts and metrics are SERVER-rendered rollups (the same query that produced the rows, so they can't disagree).
