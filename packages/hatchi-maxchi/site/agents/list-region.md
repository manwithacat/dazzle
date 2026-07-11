# List region (`list-region`)

The in-card data table: an actions row with CSV export, a horizontally scrollable table, and an overflow count.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="list-region">
  <div class="list-actions">
    <div class="list-action-group"><button type="button" class="list-csv-button" title="Export CSV" aria-label="Export CSV"><svg class="icon" aria-hidden="true"><use href="#i-download"/></svg></button></div>
  </div>
  <div class="list-scroll">
    <table class="list-table">
      <thead>
        <tr>
          <th><a href="#" class="list-sort-link">Name<span>▲</span></a></th>
          <th>Owner</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr class="list-row is-clickable">
          <td>Quarterly audit</td>
          <td>M. Reyes</td>
          <td>Active</td>
        </tr>
        <tr class="list-row ">
          <td>Vendor renewal</td>
          <td>A. Osei</td>
          <td>Draft</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="list-overflow">Showing 2 of 14</p>
</div>
```

## Notes

The CSV button is ALWAYS rendered in the actions row. The snippet omits its wiring: the real emitter adds data-dz-csv-endpoint/data-dz-csv-filename and an onclick that calls window.dz.downloadCsv(endpoint, filename) against the server export route. Sortable headers are dz-list-sort-link anchors carrying an hx-get with ?sort=<col>&dir=<asc|desc> — the server re-renders the region; the active column shows a text caret. Rows wired to a drill URL carry is-clickable; the overflow line reports what the page cut. For the full hypermedia table primitive (selection, filters, pagination) use the grid Hyperpart — this one is the lighter in-card region.
