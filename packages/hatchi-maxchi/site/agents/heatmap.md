# Heatmap (`heatmap`)

A two-dimensional grid of toned cells — rows × buckets, thresholds driving good/warn/bad tones, never colour alone (the value is IN the cell).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="heatmap-region hm-measure-lg" data-heatmap>
  <div class="heatmap-scroll">
    <table class="heatmap-grid">
      <thead>
        <tr>
          <th></th>
          <th>Mon</th>
          <th>Tue</th>
          <th>Wed</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="heatmap-row-label">API</td>
          <td class="heatmap-cell" data-heatmap-tone="good"> 99.9 </td>
          <td class="heatmap-cell" data-heatmap-tone="good"> 99.7 </td>
          <td class="heatmap-cell" data-heatmap-tone="warn"> 97.2 </td>
        </tr>
        <tr>
          <td class="heatmap-row-label">Webhooks</td>
          <td class="heatmap-cell" data-heatmap-tone="warn"> 96.1 </td>
          <td class="heatmap-cell" data-heatmap-tone="bad"> 89.4 </td>
          <td class="heatmap-cell" data-heatmap-tone="good"> 99.2 </td>
        </tr>
      </tbody>
    </table>
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

### `contracts/heatmap.py`

- **Required root:** `[data-dz-heatmap]` (part `heatmap`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-heatmap]` | `data-dz-heatmap` | present (any value) |

#### Ingestion model `HeatmapRow`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `cells` | `array` | no |

#### Exemplar `render()`

```python
def render(h: Heatmap) -> str:
    """Model → heatmap region."""
    if not h.rows:
        return (
            f'<div class="dz-heatmap-region" data-dz-heatmap>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(h.empty_message)}</p>"
            f"</div>"
        )

    head_cols = "".join(f"<th>{html.escape(c)}</th>" for c in h.columns)
    thead = f"<thead><tr><th></th>{head_cols}</tr></thead>"
    body_rows: list[str] = []
    for row in h.rows:
        cells_html = ""
        for cell in row.cells:
            cells_html += (
                f'<td class="dz-heatmap-cell"{_tone_attr(cell, h.thresholds)}> {cell:.1f} </td>'
            )
        body_rows.append(
            f'<tr><td class="dz-heatmap-row-label">{html.escape(row.label)}</td>{cells_html}</tr>'
        )
    tbody = f"<tbody>{''.join(body_rows)}</tbody>"
    overflow_html = ""
    if h.total > len(h.rows):
        overflow_html = f'<p class="dz-heatmap-overflow">Showing {len(h.rows)} of {h.total}</p>'
    return (
        f'<div class="dz-heatmap-region" data-dz-heatmap>'
        f'<div class="dz-heatmap-scroll">'
        f'<table class="dz-heatmap-grid">{thead}{tbody}</table>'
        f"</div>"
        f"{overflow_html}"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-heatmap (contracts/heatmap.py). Cell tones ride data-dz-heatmap-tone="good|warn|bad", resolved server-side against the declared thresholds — and the numeric value always renders inside the cell, so tone is reinforcement, not the only signal. Overflowing grids append a dz-heatmap-overflow count line; the scroll wrapper keeps wide grids inside their card.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/heatmap.py`
