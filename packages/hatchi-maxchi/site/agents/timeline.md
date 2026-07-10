# Timeline (`timeline`)

Dated events on a vertical line — bullets carry the attention contract, dates keep a fixed column so titles align.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="timeline-region hm-measure-lg">
  <ul class="timeline-list">
    <li class="timeline-item">
      <span class="timeline-bullet-wrap"><svg class="timeline-bullet attn-bullet attn-tone-critical" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="timeline-row">
        <div class="timeline-date">Today</div>
        <div class="timeline-content">
          <p class="timeline-title">Payment failed — retry scheduled</p>
          <p class="timeline-field">Card declined (insufficient funds)</p>
        </div>
      </div>
    </li>
    <li class="timeline-item">
      <span class="timeline-bullet-wrap"><svg class="timeline-bullet attn-bullet attn-tone-default" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="timeline-row">
        <div class="timeline-date">Mon</div>
        <div class="timeline-content">
          <p class="timeline-title">Invoice sent</p>
        </div>
      </div>
    </li>
  </ul>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The bullet is an inline SVG on <code>currentColor</code>, toned by <code>dz-attn-tone-*</code> (critical/warning/notice/default) — the shared attention vocabulary. Overflowing timelines append a <code>dz-timeline-overflow</code> count line.
