# Radar (`radar`)

Polar multi-axis profile — spokes share a scale; the polygon is server-rendered SVG.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="radar-region hm-measure-lg" data-radar>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" class="radar-svg chart-svg" role="img" aria-label="Coverage radar — 5 spokes, peak 90">
    <polygon points="160.0,128.0 190.43380852144492,150.11145618000168 178.80912807335915,185.88854381999832 141.19087192664085,185.88854381999832 129.56619147855508,150.11145618000168" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6"/>
    <polygon points="160.0,96.0 220.86761704288983,140.22291236000336 197.6182561467183,211.77708763999664 122.38174385328173,211.77708763999664 99.13238295711017,140.22291236000336" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6"/>
    <polygon points="160.0,64.0 251.30142556433475,130.33436854000504 216.4273842200774,237.66563145999496 103.57261577992259,237.66563145999496 68.69857443566525,130.33436854000507" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6"/>
    <polygon points="160.0,32.0 281.73523408577967,120.44582472000673 235.23651229343656,263.5541752799933 84.76348770656345,263.5541752799933 38.264765914220334,120.44582472000675" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6"/>
    <line x1="160.0" y1="160.0" x2="160.0" y2="32.0" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7"/>
    <line x1="160.0" y1="160.0" x2="281.73523408577967" y2="120.44582472000673" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7"/>
    <line x1="160.0" y1="160.0" x2="235.23651229343656" y2="263.5541752799933" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7"/>
    <line x1="160.0" y1="160.0" x2="84.76348770656345" y2="263.5541752799933" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7"/>
    <line x1="160.0" y1="160.0" x2="38.264765914220334" y2="120.44582472000675" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7"/>
    <polygon points="160.0,46.22222222222223 247.91989128417418,131.43309563111598 235.23651229343656,263.5541752799933 101.48271266066047,240.54213632888366 85.60624583646798,135.82800399555967" fill="var(--colour-brand)" fill-opacity="0.15" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round"/>
    <circle cx="160.0" cy="46.22222222222223" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>Auth value: 80</title>
    </circle>
    <circle cx="247.91989128417418" cy="131.43309563111598" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>API value: 65</title>
    </circle>
    <circle cx="235.23651229343656" cy="263.5541752799933" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>UI value: 90</title>
    </circle>
    <circle cx="101.48271266066047" cy="240.54213632888366" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>Data value: 70</title>
    </circle>
    <circle cx="85.60624583646798" cy="135.82800399555967" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1">
      <title>Ops value: 55</title>
    </circle>
    <text x="160.0" y="18.0" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">Auth</text>
    <text x="295.05002531391176" y="116.11958679875747" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">API</text>
    <text x="243.46550582553118" y="274.8804132012425" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">UI</text>
    <text x="76.53449417446883" y="274.8804132012425" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">Data</text>
    <text x="24.949974686088183" y="116.1195867987575" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">Ops</text>
  </svg>
  <p class="chart-summary">5 spokes · 1 series · peak 90</p>
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
