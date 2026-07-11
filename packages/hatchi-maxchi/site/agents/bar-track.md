# Bar track (`bar-track`)

Value-against-capacity rows with real progressbar semantics — the resource-usage sibling of the bar chart.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="bar-track-region hm-measure-lg" data-bar-track>
  <div class="bar-track-rows">
    <div class="bar-track-row">
      <span class="bar-track-label" title="Storage">Storage</span>
      <div class="bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="62" aria-label="Storage: 62%"><span class="bar-track-fill" style="width: 62%;" title="Storage: 62%"></span></div>
      <span class="bar-track-value">62%</span>
    </div>
    <div class="bar-track-row">
      <span class="bar-track-label" title="Compute">Compute</span>
      <div class="bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="38" aria-label="Compute: 38%"><span class="bar-track-fill" style="width: 38%;" title="Compute: 38%"></span></div>
      <span class="bar-track-value">38%</span>
    </div>
  </div>
  <p class="bar-track-summary">2 rows · scale 0–100</p>
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

### `contracts/bar_track.py`

- **Required root:** `[data-dz-bar-track]` (part `bar-track`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-bar-track]` | `data-dz-bar-track` | present (any value) |

#### Ingestion model `BarTrackRow`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `value` | `number` | no |
| `formatted` | `string` | no |
| `fill_pct` | `number` | no |

#### Exemplar `render()`

```python
def render(b: BarTrack) -> str:
    """Model → bar-track region (references block is host-local)."""
    if not b.rows:
        return '<div class="dz-bar-track-region" data-dz-bar-track></div>'

    max_str = _num(b.max_value)
    rows_html = "".join(
        f'<div class="dz-bar-track-row">'
        f'<span class="dz-bar-track-label" title="{html.escape(row.label, quote=True)}">'
        f"{html.escape(row.label)}</span>"
        f'<div class="dz-bar-track" role="progressbar" '
        f'aria-valuemin="0" '
        f'aria-valuemax="{max_str}" '
        f'aria-valuenow="{_num(row.value)}" '
        f'aria-label="{html.escape(row.label, quote=True)}: '
        f'{html.escape(row.formatted or _num(row.value), quote=True)}">'
        f'<span class="dz-bar-track-fill" '
        f'style="width: {_num(round(row.fill_pct, 2))}%;" '
        f'title="{html.escape(row.label, quote=True)}: '
        f'{html.escape(row.formatted or _num(row.value), quote=True)}"></span>'
        f"</div>"
        f'<span class="dz-bar-track-value">'
        f"{html.escape(row.formatted or _num(row.value))}</span>"
        f"</div>"
        for row in b.rows
    )
    max_rounded = round(b.max_value, 2)
    max_summary = str(int(max_rounded)) if max_rounded == int(max_rounded) else str(max_rounded)
    return (
        f'<div class="dz-bar-track-region" data-dz-bar-track>'
        f'<div class="dz-bar-track-rows">{rows_html}</div>'
        f'<p class="dz-bar-track-summary">'
        f"{len(b.rows)} rows · scale 0–{max_summary}"
        f"</p>"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-bar-track (contracts/bar_track.py). Each track is a real role="progressbar" with numeric aria values — the fill width is presentation, the aria is the content. Labels and fills both carry title for hover detail.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/bar_track.py`
