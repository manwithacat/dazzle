# Bar chart (`bar-chart`)

Label / track / value rows — the workhorse categorical chart, server-computed and scope-safe.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="bar-chart-region hm-measure-lg">
  <div class="bar-chart-bars">
    <div class="bar-chart-row">
      <span class="bar-chart-label">API</span>
      <div class="bar-chart-track">
        <div class="bar-chart-fill" style="width: 84%"></div>
      </div>
      <span class="bar-chart-value">126</span>
    </div>
    <div class="bar-chart-row">
      <span class="bar-chart-label">Dashboard</span>
      <div class="bar-chart-track">
        <div class="bar-chart-fill" style="width: 56%"></div>
      </div>
      <span class="bar-chart-value">84</span>
    </div>
    <div class="bar-chart-row">
      <span class="bar-chart-label">Billing</span>
      <div class="bar-chart-track">
        <div class="bar-chart-fill" style="width: 23%"></div>
      </div>
      <span class="bar-chart-value">35</span>
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

In Dazzle every bar chart compiles to ONE scope-aware GROUP BY — the bucket list and the counts come from the same query, so they cannot disagree (the #847-class bug this design retired). Fill widths are server-computed percentages of the max bucket.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
