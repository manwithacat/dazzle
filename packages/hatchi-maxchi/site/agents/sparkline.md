# Sparkline (`sparkline`)

A headline number with its recent shape — the smallest chart: a current value, its bucket label, and an area glyph.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="sparkline-region" data-sparkline>
  <div class="sparkline-headline"><span class="sparkline-value">184ms</span><span class="sparkline-bucket-label">this hour</span></div>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 32" class="sparkline-svg" role="img" aria-label="Sparkline — 12 points, latest 184ms, peak 240ms"><polygon points="0,32 0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 144,14 162,6 180,9 180,32" fill="var(--colour-brand)" fill-opacity="0.15" stroke="none"/><polyline points="0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 144,14 162,6 180,9" fill="none" stroke="var(--colour-brand)" stroke-width="1.25" stroke-linejoin="round" stroke-linecap="round"/></svg>
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

### `contracts/sparkline.py`

- **Required root:** `[data-dz-sparkline]` (part `sparkline`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-sparkline]` | `data-dz-sparkline` | present (any value) |

#### Ingestion model `Sparkline`

| Field | Type | Required |
|---|---|---|
| `points` | `array` | no |
| `empty_message` | `string` | no |

#### Exemplar `render()`

```python
def render(s: Sparkline) -> str:
    """Model → sparkline region (matches Dazzle emitter geometry)."""
    if not s.points:
        return (
            f'<div class="dz-sparkline-region" data-dz-sparkline>'
            f'<div class="dz-sparkline-empty">{html.escape(s.empty_message)}</div>'
            f"</div>"
        )

    last_label, last_value = s.points[-1]
    last_value_str = str(int(last_value)) if last_value == int(last_value) else str(last_value)
    max_val = max(v for _, v in s.points)
    if max_val <= 0:
        max_val = 1.0
    max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)
    count = len(s.points)

    headline = (
        f'<div class="dz-sparkline-headline">'
        f'<span class="dz-sparkline-value">{html.escape(last_value_str)}</span>'
        f'<span class="dz-sparkline-bucket-label">{html.escape(last_label)}</span>'
        f"</div>"
    )

    if count <= 1:
        return f'<div class="dz-sparkline-region" data-dz-sparkline>{headline}</div>'

    w, h, pt, pb = 180, 32, 2, 2
    plot_h = h - pt - pb
    step = w / (count - 1)
    pts = []
    for i, (_, v) in enumerate(s.points):
        x = round(i * step, 2)
        y = round(pt + plot_h - (v / max_val * plot_h), 2)
        pts.append(f"{x},{y}")
    pts_str = " ".join(pts)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" '
        f'class="dz-sparkline-svg" role="img" '
        f'aria-label="Sparkline — {count} points, latest '
        f'{html.escape(last_value_str)}, peak {html.escape(max_val_str)}">'
        f'<polygon points="0,{h} {pts_str} {w},{h}" '
        f'fill="var(--colour-brand)" fill-opacity="0.15" stroke="none" />'
        f'<polyline points="{pts_str}" fill="none" '
        f'stroke="var(--colour-brand)" stroke-width="1.25" '
        f'stroke-linejoin="round" stroke-linecap="round" />'
        f"</svg>"
    )
    return f'<div class="dz-sparkline-region" data-dz-sparkline>{headline}{svg}</div>'
```

## Notes

Dual-lock root is data-dz-sparkline (contracts/sparkline.py). The SVG is server-rendered with a numeric summary in aria-label (points / latest / peak) — the glyph is decoration; the numbers are the content. An empty series renders dz-sparkline-empty; a single point renders the headline alone.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/sparkline.py`
