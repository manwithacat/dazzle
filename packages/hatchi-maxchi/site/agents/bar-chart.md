# Bar chart (`bar-chart`)

Label / track / value rows — the workhorse categorical chart, server-computed and scope-safe.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="bar-chart-region hm-measure-lg" data-bar-chart>
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
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/bar_chart.py`

- **Required root:** `[data-dz-bar-chart]` (part `bar-chart`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-bar-chart]` | `data-dz-bar-chart` | present (any value) |

#### Ingestion model `BarChartRow`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `count` | `integer` | no |
| `width_pct` | `integer` | no |
| `label_html` | `string` | no |

#### Exemplar `render()`

```python
def render(chart: BarChart) -> str:
    """Model → bar chart region."""
    if not chart.rows:
        return '<div class="dz-bar-chart-region" data-dz-bar-chart></div>'

    rows_html = "".join(
        f'<div class="dz-bar-chart-row">'
        f'<span class="dz-bar-chart-label">'
        f"{(row.label_html if row.label_html.strip() else html.escape(row.label))}"
        f"</span>"
        f'<div class="dz-bar-chart-track">'
        f'<div class="dz-bar-chart-fill" '
        f'style="width: {max(0, min(100, row.width_pct))}%"></div>'
        f"</div>"
        f'<span class="dz-bar-chart-value">{row.count}</span>'
        f"</div>"
        for row in chart.rows
    )
    return (
        f'<div class="dz-bar-chart-region" data-dz-bar-chart>'
        f'<div class="dz-bar-chart-bars">{rows_html}</div>'
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-bar-chart (contracts/bar_chart.py). In Dazzle every bar chart compiles to ONE scope-aware GROUP BY — the bucket list and the counts come from the same query, so they cannot disagree (the #847-class bug this design retired). Fill widths are server-computed percentages of the max bucket.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/bar_chart.py`
