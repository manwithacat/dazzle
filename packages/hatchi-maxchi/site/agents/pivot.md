# Pivot table (`pivot`)

Two group-bys crossed into a matrix — row labels × column buckets, empty intersections rendered as explicit nulls.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="pivot-region hm-measure-lg">
  <div class="pivot-scroll">
    <table class="pivot-grid">
      <thead>
        <tr>
          <th>System</th>
          <th>Severity</th>
          <th class="is-measure">Count</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>API</td>
          <td><span class="badge badge-sm" data-tone="destructive" role="status" aria-label="Status: Critical"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-x"/></svg></span>Critical</span></td>
          <td class="is-measure">3</td>
        </tr>
        <tr>
          <td>Dashboard</td>
          <td><span class="pivot-null">—</span></td>
          <td class="is-measure">9</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="pivot-summary">2 rows</p>
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

One scope-aware two-dimensional GROUP BY fills the whole matrix: dimension columns lead (status values render as badges, FK values as their label text), then measure columns — class="is-measure" on the measure th/td pair drives the mono right-aligned numeric treatment. Empty intersections render dz-pivot-null em-dashes rather than blanks (absence is data). The scroll wrapper keeps wide matrices inside their card.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
