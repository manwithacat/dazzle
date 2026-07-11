# Progress stages (`progress-region`)

A native progress bar with stage chips — where the work is, stage by stage, with completion tones.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="progress-region hm-measure-lg">
  <div class="progress-header">
    <progress data-progress value="33" max="100"></progress>
    <span>33%</span>
  </div>
  <div class="progress-stages"><span class="progress-chip" data-stage-tone="complete">Draft (4)</span><span class="progress-chip" data-stage-tone="active">Review (2)</span><span class="progress-chip" data-stage-tone="empty">Published (0)</span></div>
  <p class="progress-summary">1 of 3 complete</p>
</div>
```

## Notes

The bar is a NATIVE <progress> (styled via data-dz-progress) with its percent readout as a plain <span> beside it in the header; chips are plain text (Name (count)) toned by data-dz-stage-tone="complete|active|empty"; the summary paragraph follows the stages.
