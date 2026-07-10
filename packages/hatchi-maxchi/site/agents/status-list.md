# Status list (`status-list`)

System / check states as an icon + title + caption list — tone rides data-dz-state per row, never colour alone.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="status-list-region hm-measure-lg">
  <ul class="status-list" data-entry-count="3">
    <li class="status-list-entry" data-state="success">
      <span class="status-list-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>
      <div class="status-list-text">
        <div class="status-list-title">Payments API</div>
        <div class="status-list-caption">Operational · 99.99% this month</div>
      </div>
      <span class="status-list-pill">success</span>
    </li>
    <li class="status-list-entry" data-state="warning">
      <span class="status-list-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>
      <div class="status-list-text">
        <div class="status-list-title">Webhooks</div>
        <div class="status-list-caption">Elevated retries since 09:20</div>
      </div>
      <span class="status-list-pill">warning</span>
    </li>
    <li class="status-list-entry" data-state="neutral">
      <span class="status-list-icon-spacer" aria-hidden="true"></span>
      <div class="status-list-text">
        <div class="status-list-title">Nightly export</div>
        <div class="status-list-caption">Scheduled 02:00</div>
      </div>
    </li>
  </ul>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Per-row state is <code>data-dz-state</code> on the entry (the pill repeats it as text for WCAG 1.4.1); a neutral row has no pill and an icon SPACER keeps the text column aligned. The wrapper's <code>data-dz-entry-count</code> is the server's row count — handy for e2e assertions without counting DOM.
