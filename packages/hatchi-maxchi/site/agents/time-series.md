# Time series (`time-series`)

Line or area sequential chart — one series of (label, value) points, or multi-series overlays with a shared legend.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="line-chart-region hm-measure-lg" data-time-series>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" role="img" aria-label="Line chart — 3 buckets"><polyline points="4,30 90,10 176,34" fill="none" stroke="var(--colour-brand)" stroke-width="2"/></svg>
  <p class="chart-summary">3 buckets · peak 18</p>
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

### `contracts/time_series.py`

- **Required root:** `[data-dz-time-series]` (part `time-series`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-time-series]` | `data-dz-time-series` | present (any value) |

#### Ingestion model `TimeSeriesPoint`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `value` | `number` | no |

#### Exemplar `render()`

```python
def render(t: TimeSeries) -> str:
    """Model → line/area chart region."""
    cls = _wrapper_class(t.view)
    if not t.points and not t.series:
        if t.empty_message:
            return (
                f'<div class="{cls}" data-dz-time-series>'
                f'<p class="dz-empty-dense" role="status">'
                f"{html.escape(t.empty_message)}</p>"
                f"</div>"
            )
        return f'<div class="{cls}" data-dz-time-series></div>'

    if t.series:
        axis_labels = {p.label for layer in t.series for p in layer.points}
        peak = t.peak_display
        if not peak:
            vals = [p.value for layer in t.series for p in layer.points]
            max_val = max(vals, default=0) or 0
            peak = str(int(max_val)) if max_val == int(max_val) else str(max_val)
        summary = (
            f'<p class="dz-chart-summary">{len(axis_labels)} buckets · '
            f"{len(t.series)} series · peak {html.escape(peak)}</p>"
        )
        return f'<div class="{cls}" data-dz-time-series>{t.svg_html}{t.legend_html}{summary}</div>'

    peak = t.peak_display
    if not peak:
        max_val = max((p.value for p in t.points), default=0) or 0
        peak = str(int(max_val)) if max_val == int(max_val) else str(max_val)
    summary = f'<p class="dz-chart-summary">{len(t.points)} buckets · peak {html.escape(peak)}</p>'
    return f'<div class="{cls}" data-dz-time-series>{t.svg_html}{summary}</div>'
```

## Notes

Dual-lock root is data-dz-time-series (contracts/time_series.py). Wrapper class stays view-specific (dz-line-chart-region / dz-area-chart-region). Multi-series charts append a trusted legend; SVG geometry comes from dazzle.render.svg.time_series_svg.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/time_series.py`
