# Action grid (`action-grid`)

Tone-tinted CTA cards with a count badge — the dashboard's 'what needs doing' surface. Cards with a URL are anchors; the grid packs intrinsically.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="action-grid-region">
  <div class="action-grid">
    <a class="action-card" data-tone="warning" href="#">
      <div class="action-card-row"><span class="action-card-icon"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span><span class="action-card-count" data-tone-badge="warning">3</span></div>
      <span class="action-card-label">Overdue invoices</span>
    </a>
    <a class="action-card" data-tone="accent" href="#">
      <div class="action-card-row"><span class="action-card-icon"><svg class="icon" aria-hidden="true"><use href="#i-receipt"/></svg></span><span class="action-card-count" data-tone-badge="accent">12</span></div>
      <span class="action-card-label">Awaiting approval</span>
    </a>
    <div class="action-card" data-tone="neutral">
      <div class="action-card-row"><span class="action-card-icon-spacer"></span></div>
      <span class="action-card-label">Nothing else today</span>
    </div>
  </div>
</div>
```

## Notes

Tone tints the card surface via data-dz-tone and the count badge via data-dz-tone-badge. A URL makes the card an <a> (whole card = the target); without one it renders a static <div>. An icon SPACER holds the row height when a card has no icon.
