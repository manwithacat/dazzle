# Metric tiles (`metrics`)

The KPI strip: label + value tiles in a packing grid, optionally toned. The server stamps the tile count for e2e anchors.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="metrics-grid" data-tile-count="3">
  <div class="metric-tile" data-metric-key="outstanding">
    <div class="metric-label">Outstanding</div>
    <div class="metric-value">£12,450</div>
  </div>
  <div class="metric-tile" data-metric-key="paid" data-tone="positive">
    <div class="metric-label">Paid this month</div>
    <div class="metric-value">£48,900</div>
  </div>
  <div class="metric-tile" data-metric-key="overdue" data-tone="warning">
    <div class="metric-label">Overdue</div>
    <div class="metric-value">3</div>
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

Each tile carries data-dz-metric-key (a stable anchor for tests/telemetry) and an optional data-dz-tone. In Dazzle one scope-aware GROUP BY query fills the whole strip — the tiles can never disagree with each other.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
