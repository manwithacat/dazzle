# Task inbox (`task-inbox`)

The personal worklist: filter chips over urgency-flagged items, each a drill link with title and meta.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="hm-measure-lg">
  <div class="task-inbox-chips">
    <div class="task-inbox-chip" data-chip-id="all"><span class="task-inbox-chip-count">6</span><span class="task-inbox-chip-label">All</span></div>
    <div class="task-inbox-chip" data-chip-id="overdue"><span class="task-inbox-chip-count">2</span><span class="task-inbox-chip-label">Overdue</span></div>
  </div>
  <ul class="task-inbox-items">
    <li class="task-inbox-item" data-urgency="overdue" data-item-id="t1">
      <a class="task-inbox-item-link" href="#">
        <span class="task-inbox-item-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-inbox"/></svg></span>
        <div class="task-inbox-item-body">
          <div class="task-inbox-item-title">Approve refund — Acme</div>
          <div class="task-inbox-item-meta">due in 2h · assigned to you</div>
        </div>
      </a>
    </li>
    <li class="task-inbox-item" data-urgency="due" data-item-id="t2">
      <a class="task-inbox-item-link" href="#">
        <span class="task-inbox-item-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-inbox"/></svg></span>
        <div class="task-inbox-item-body">
          <div class="task-inbox-item-title">Review KYC — Globex</div>
          <div class="task-inbox-item-meta">due tomorrow</div>
        </div>
      </a>
    </li>
  </ul>
</div>
```

## Notes

Items carry data-dz-urgency="overdue|due|soon|later" (the server clamps anything else to later) + a stable data-dz-item-id; the whole row is one link, leading with its icon. Chips render count THEN label (data-dz-chip-id anchors a filter exchange in Dazzle).
