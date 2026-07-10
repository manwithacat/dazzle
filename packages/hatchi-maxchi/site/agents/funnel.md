# Funnel (`funnel`)

Stage-by-stage narrowing — each bar's width is the stage's share, with a total summary line.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="funnel-chart-region hm-measure-lg">
  <div class="funnel-stages">
    <div class="funnel-stage-row">
      <div class="funnel-stage" data-funnel-step="0" style="width: 100%;"><span class="funnel-stage-label">Visited</span><span class="funnel-stage-count"> (1,204)</span></div>
    </div>
    <div class="funnel-stage-row">
      <div class="funnel-stage" data-funnel-step="1" style="width: 62%;"><span class="funnel-stage-label">Signed up</span><span class="funnel-stage-count"> (746)</span></div>
    </div>
    <div class="funnel-stage-row">
      <div class="funnel-stage" data-funnel-step="2" style="width: 28%;"><span class="funnel-stage-label">Subscribed</span><span class="funnel-stage-count"> (338)</span></div>
    </div>
  </div>
  <p class="funnel-summary">1,204 total</p>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Widths are SERVER-computed percentages on inline style — the one place inline style is the contract (a per-row datum, like the progress knob). <code>data-dz-funnel-step</code> tones the stages in sequence.
