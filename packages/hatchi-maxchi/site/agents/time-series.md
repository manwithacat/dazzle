# Time series (`time-series`)

Line or area sequential chart — one series of (label, value) points, or multi-series overlays with a shared legend.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="line-chart-region hm-measure-lg" data-time-series>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="line-chart-svg chart-svg" role="img" aria-label="Traffic time series — 14 buckets, peak 91">
    <line x1="8" y1="92" x2="392" y2="92" stroke="var(--colour-border)" stroke-width="1"/>
    <polygon points="8,92 8.0,53.23 37.54,44.92 67.08,47.69 96.62,33.85 126.15,26.46 155.69,56.92 185.23,59.69 214.77,38.46 244.31,31.08 273.85,25.54 303.38,18.15 332.92,8.0 362.46,48.62 392.0,51.38 392,92" fill="var(--colour-brand)" fill-opacity="0.12" stroke="none"/>
    <polyline points="8.0,53.23 37.54,44.92 67.08,47.69 96.62,33.85 126.15,26.46 155.69,56.92 185.23,59.69 214.77,38.46 244.31,31.08 273.85,25.54 303.38,18.15 332.92,8.0 362.46,48.62 392.0,51.38" fill="none" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="8.0" cy="53.23" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>3 Mar: 42</title>
    </circle>
    <circle cx="37.54" cy="44.92" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>4 Mar: 51</title>
    </circle>
    <circle cx="67.08" cy="47.69" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>5 Mar: 48</title>
    </circle>
    <circle cx="96.62" cy="33.85" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>6 Mar: 63</title>
    </circle>
    <circle cx="126.15" cy="26.46" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>7 Mar: 71</title>
    </circle>
    <circle cx="155.69" cy="56.92" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>8 Mar: 38</title>
    </circle>
    <circle cx="185.23" cy="59.69" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>9 Mar: 35</title>
    </circle>
    <circle cx="214.77" cy="38.46" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>10 Mar: 58</title>
    </circle>
    <circle cx="244.31" cy="31.08" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>11 Mar: 66</title>
    </circle>
    <circle cx="273.85" cy="25.54" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>12 Mar: 72</title>
    </circle>
    <circle cx="303.38" cy="18.15" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>13 Mar: 80</title>
    </circle>
    <circle cx="332.92" cy="8.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>14 Mar: 91</title>
    </circle>
    <circle cx="362.46" cy="48.62" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>15 Mar: 47</title>
    </circle>
    <circle cx="392.0" cy="51.38" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>16 Mar: 44</title>
    </circle>
    <text x="8.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">3 Mar</text>
    <text x="96.62" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">6 Mar</text>
    <text x="185.23" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">9 Mar</text>
    <text x="273.85" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">12 Mar</text>
    <text x="362.46" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">15 Mar</text>
    <text x="392.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">16 Mar</text>
  </svg>
  <p class="chart-summary">14 buckets · peak 91</p>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

**No host HTMX exchange** on this part — presentation or client chrome only. **Exchange envelope:** `n/a`.

If a **host** wraps this markup in `hx-*`, **that host owns the swap contract** (sole identity + envelope). Prefer `innerMorph` / `outerMorph` for stable slots; replacement for flash; body-only responses under inner swaps.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

This part has no owned exchange (envelope `n/a`). If a host adds `hx-*`, that host’s envelope applies — typically `body_only`:

```html
<!-- Prefer hx-swap=innerMorph into a stable body slot -->
<div class="dz-stack">content…</div>
```

Do **not** re-own the slot:

```html
<div id="time-series-root" data-dz-region>…</div>
```

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
