# Bullet chart (`bullet`)

Actual vs target on qualitative bands — the KPI-with-context bar. All geometry is server-computed inline percentages.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

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

## Notes

Bands, the actual bar, and the target tick are absolutely positioned by SERVER-computed inline percentages (per-row data, the same contract as the funnel widths); each carries a title with its numeric range. Band fills come from the server's reference-band colour map (target → var(--colour-brand), destructive → var(--colour-danger), plus fixed positive/warning/muted values) — saturated colours, because the band layer renders at 0.18 opacity. The value (and target, when set) renders as text beside the track; the mono summary line carries row count and scale.
