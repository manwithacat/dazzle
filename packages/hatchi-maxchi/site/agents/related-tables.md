# Related records (`related-tables`)

A detail view's companions: tabbed groups of related records — status cards, a compact table, or a file list — each tab counted.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

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

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

One dz-related-group per related entity. The tab strip IS the tabs Hyperpart (dz-tabs__tab + data-dz-tab-target, driven by dz-tabs.js) with a related-specific count chip; panels are native-hidden toggles. Three body shapes share the chrome: the status-card grid (shown), a compact dz-related-table, and a dz-related-file-list. In Dazzle these render from the detail view's related groups — the same shared cell core as list rows, so badges/dates match.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
