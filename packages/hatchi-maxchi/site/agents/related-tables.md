# Related records (`related-tables`)

A detail view's companions: tabbed groups of related records — status cards, a compact table, or a file list — each tab counted.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="related-group hm-measure-lg">
  <div class="tabs">
    <div class="tabs__list"><button type="button" class="tabs__tab" aria-current="true" data-tab-target="hm-rel-invoices">Invoices<span class="related-tab-count">2</span></button><button type="button" class="tabs__tab" data-tab-target="hm-rel-files">Files<span class="related-tab-count">1</span></button></div>
    <div id="hm-rel-invoices" class="tabs__panel">
      <div class="related-status-grid">
        <div class="related-status-card">
          <div class="related-status-card-row">
            <div class="related-status-card-text"><span class="related-status-card-primary">INV-001 · £1,250</span><span class="related-status-card-secondary">due 12 Jul</span></div>
            <span class="related-status-card-badge"><span class="badge" data-tone="success">Paid</span></span>
          </div>
        </div>
        <div class="related-status-card">
          <div class="related-status-card-row">
            <div class="related-status-card-text"><span class="related-status-card-primary">INV-002 · £980</span><span class="related-status-card-secondary">due 28 Jul</span></div>
            <span class="related-status-card-badge"><span class="badge" data-tone="warning"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>Overdue</span></span>
          </div>
        </div>
      </div>
    </div>
    <div id="hm-rel-files" class="tabs__panel" hidden>
      <div class="related-status-grid">
        <div class="related-status-card">
          <div class="related-status-card-row">
            <div class="related-status-card-text"><span class="related-status-card-primary">contract.pdf</span><span class="related-status-card-secondary">uploaded 3 Jul</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

One <code>dz-related-group</code> per related entity. The tab strip IS the tabs Hyperpart (<code>dz-tabs__tab</code> + <code>data-dz-tab-target</code>, driven by dz-tabs.js) with a related-specific count chip; panels are native-<code>hidden</code> toggles. Three body shapes share the chrome: the status-card grid (shown), a compact <code>dz-related-table</code>, and a <code>dz-related-file-list</code>. In Dazzle these render from the detail view's related groups — the same shared cell core as list rows, so badges/dates match.
