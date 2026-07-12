# Radar (`radar`)

Polar multi-axis profile — spokes share a scale; the polygon is server-rendered SVG.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="radar-region hm-measure-lg" data-radar>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="Radar — 3 spokes"><polygon points="60,20 100,90 20,90" fill="var(--colour-brand)" fill-opacity="0.25" stroke="var(--colour-brand)"/></svg>
  <p class="chart-summary">3 spokes · 1 series · peak 90</p>
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

### `contracts/radar.py`

- **Required root:** `[data-dz-radar]` (part `radar`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-radar]` | `data-dz-radar` | present (any value) |

#### Ingestion model `RadarAxis`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `value` | `number` | no |

#### Exemplar `render()`

```python
def render(r: Radar) -> str:
    """Model → radar region."""
    if not r.axes:
        return (
            f'<div class="dz-radar-region" data-dz-radar>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(r.empty_message)}</p>"
            f"</div>"
        )
    peak = r.peak_display
    if not peak:
        max_val = max((a.value for a in r.axes), default=0) or 0
        peak = str(int(max_val)) if max_val == int(max_val) else str(max_val)
    summary = (
        f'<p class="dz-chart-summary">'
        f"{len(r.axes)} spokes · 1 series · peak {html.escape(peak)}"
        f"</p>"
    )
    return f'<div class="dz-radar-region" data-dz-radar>{r.svg_html}{summary}</div>'
```

## Notes

Dual-lock root is data-dz-radar (contracts/radar.py). Geometry rides trusted svg_html from dazzle.render.svg.radar_svg; the summary carries spoke count and peak.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/radar.py`
