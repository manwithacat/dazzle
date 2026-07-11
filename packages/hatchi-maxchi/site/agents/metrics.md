# Metric tiles (`metrics`)

The KPI strip: label + value tiles in a packing grid, optionally toned. The server stamps the tile count for e2e anchors.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

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
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/metrics.py`

- **Required root:** `[data-dz-metric-key]` (part `metrics`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-metric-key]` | `data-dz-metric-key` | present (any value) |

#### Ingestion model `MetricTile`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `value` | `string` | yes |
| `metric_key` | `string` | no |
| `tone` | `string ∈ ['', 'positive', 'warning', 'destructive', 'accent', 'neutral']` | no |
| `delta_direction` | `string ∈ ['', 'up', 'down', 'flat']` | no |
| `delta_sentiment` | `string ∈ ['', 'positive_up', 'positive_down']` | no |
| `delta_value` | `string` | no |
| `delta_pct` | `number` | no |
| `delta_period_label` | `string` | no |

#### Exemplar `render()`

```python
def render(tile: MetricTile) -> str:
    """Model → one metric tile."""
    key = html.escape(tile.metric_key, quote=True)
    label = html.escape(tile.label)
    value = html.escape(tile.value)
    tone_attr = ""
    if tile.tone:
        tone_attr = f' data-dz-tone="{html.escape(tile.tone, quote=True)}"'

    delta_html = ""
    if tile.delta_direction:
        is_good = (tile.delta_direction == "up" and tile.delta_sentiment == "positive_up") or (
            tile.delta_direction == "down" and tile.delta_sentiment == "positive_down"
        )
        is_bad = (tile.delta_direction == "down" and tile.delta_sentiment == "positive_up") or (
            tile.delta_direction == "up" and tile.delta_sentiment == "positive_down"
        )
        delta_tone = "positive" if is_good else ("destructive" if is_bad else "neutral")
        arrow = (
            "↑"
            if tile.delta_direction == "up"
            else ("↓" if tile.delta_direction == "down" else "→")
        )
        sign = "+" if tile.delta_direction == "up" else ""
        pct_html = (
            f'<span class="dz-metric-delta-pct">({tile.delta_pct}%)</span>'
            if tile.delta_pct
            else ""
        )
        period_html = (
            f'<span class="dz-metric-delta-period">vs {html.escape(tile.delta_period_label)}</span>'
        )
        delta_html = (
            f'<div class="dz-metric-delta" '
            f'data-dz-delta-tone="{delta_tone}" '
            f'data-dz-delta-direction="{html.escape(tile.delta_direction, quote=True)}" '
            f'data-dz-delta-sentiment="{html.escape(tile.delta_sentiment, quote=True)}">'
            f'<span aria-hidden="true">{arrow}</span>'
            f'<span class="dz-metric-delta-value">{sign}{html.escape(tile.delta_value)}</span>'
            f"{pct_html}"
            f"{period_html}"
            f"</div>"
        )

    return (
        f'<div class="dz-metric-tile" data-dz-metric-key="{key}"{tone_attr}>'
        f'<div class="dz-metric-label">{label}</div>'
        f'<div class="dz-metric-value">{value}</div>'
        f"{delta_html}"
        f"</div>"
    )
```

## Notes

Each tile carries data-dz-metric-key (dual-lock root; contracts/metrics.py) and an optional data-dz-tone. In Dazzle one scope-aware GROUP BY query fills the whole strip — the tiles can never disagree with each other.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/metrics.py`
