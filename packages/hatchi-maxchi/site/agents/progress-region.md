# Progress stages (`progress-region`)

A native progress bar with stage chips — where the work is, stage by stage, with completion tones.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

The bar is a NATIVE <code>&lt;progress&gt;</code> (styled via <code>data-dz-progress</code>) with its percent readout as a plain <code>&lt;span&gt;</code> beside it in the header; chips are plain text (<code>Name (count)</code>) toned by <code>data-dz-stage-tone=&quot;complete|active|empty&quot;</code>; the summary paragraph follows the stages.
