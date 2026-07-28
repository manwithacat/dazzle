# Box plot (`box-plot`)

Distribution five-number summaries per bucket — a server-rendered SVG with the counts in the summary line.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="box-plot-region hm-measure-lg" data-box-plot>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 232 200" class="box-plot-svg" role="img" aria-label="Latency box plot — 3 groups, range 5.0–95.0">
    <line x1="32" y1="168" x2="224" y2="168" stroke="var(--colour-border)" stroke-width="1"/>
    <line x1="32" y1="8" x2="32" y2="168" stroke="var(--colour-border)" stroke-width="1"/>
    <text x="28" y="172" text-anchor="end" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">5.0</text>
    <text x="28" y="12" text-anchor="end" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">95.0</text>
    <line class="box-plot-whisker" x1="64.0" y1="159.11" x2="64.0" y2="141.33" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker" x1="64.0" y1="96.89" x2="64.0" y2="34.67" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker-cap" x1="55.0" y1="159.11" x2="73.0" y2="159.11" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker-cap" x1="55.0" y1="34.67" x2="73.0" y2="34.67" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <rect class="box-plot-box" x="46.0" y="96.89" width="36" height="44.44" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1">
      <title>API: Q1 20.0, median 30.0, Q3 45.0, n=120</title>
    </rect>
    <line class="box-plot-median" x1="46.0" y1="123.56" x2="82.0" y2="123.56" stroke="var(--colour-brand)" stroke-width="1"/>
    <g class="box-plot-mark" data-box-mark="max">
      <circle class="box-plot-mark-hit" cx="64.0" cy="34.67" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="64.0" cy="34.67" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="88.0" y="37.67" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">80</text>
      <title>API max: 80</title>
    </g>
    <g class="box-plot-mark" data-box-mark="q3">
      <circle class="box-plot-mark-hit" cx="64.0" cy="96.89" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="64.0" cy="96.89" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="88.0" y="99.89" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">45</text>
      <title>API q3: 45</title>
    </g>
    <g class="box-plot-mark" data-box-mark="median">
      <circle class="box-plot-mark-hit" cx="64.0" cy="123.56" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="64.0" cy="123.56" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="88.0" y="126.56" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">30</text>
      <title>API median: 30</title>
    </g>
    <g class="box-plot-mark" data-box-mark="q1">
      <circle class="box-plot-mark-hit" cx="64.0" cy="141.33" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="64.0" cy="141.33" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="88.0" y="144.33" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">20</text>
      <title>API q1: 20</title>
    </g>
    <g class="box-plot-mark" data-box-mark="min">
      <circle class="box-plot-mark-hit" cx="64.0" cy="159.11" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="64.0" cy="159.11" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="88.0" y="162.11" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">10</text>
      <title>API min: 10</title>
    </g>
    <text x="64.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">API</text>
    <line class="box-plot-whisker" x1="128.0" y1="168.0" x2="128.0" y2="150.22" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker" x1="128.0" y1="105.78" x2="128.0" y2="52.44" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker-cap" x1="119.0" y1="168.0" x2="137.0" y2="168.0" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker-cap" x1="119.0" y1="52.44" x2="137.0" y2="52.44" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <rect class="box-plot-box" x="110.0" y="105.78" width="36" height="44.44" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1">
      <title>Web: Q1 15.0, median 25.0, Q3 40.0, n=98</title>
    </rect>
    <line class="box-plot-median" x1="110.0" y1="132.44" x2="146.0" y2="132.44" stroke="var(--colour-brand)" stroke-width="1"/>
    <g class="box-plot-mark" data-box-mark="max">
      <circle class="box-plot-mark-hit" cx="128.0" cy="52.44" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="128.0" cy="52.44" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="152.0" y="55.44" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">70</text>
      <title>Web max: 70</title>
    </g>
    <g class="box-plot-mark" data-box-mark="q3">
      <circle class="box-plot-mark-hit" cx="128.0" cy="105.78" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="128.0" cy="105.78" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="152.0" y="108.78" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">40</text>
      <title>Web q3: 40</title>
    </g>
    <g class="box-plot-mark" data-box-mark="median">
      <circle class="box-plot-mark-hit" cx="128.0" cy="132.44" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="128.0" cy="132.44" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="152.0" y="135.44" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">25</text>
      <title>Web median: 25</title>
    </g>
    <g class="box-plot-mark" data-box-mark="q1">
      <circle class="box-plot-mark-hit" cx="128.0" cy="150.22" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="128.0" cy="150.22" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="152.0" y="153.22" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">15</text>
      <title>Web q1: 15</title>
    </g>
    <g class="box-plot-mark" data-box-mark="min">
      <circle class="box-plot-mark-hit" cx="128.0" cy="168.0" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="128.0" cy="168.0" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="152.0" y="171.0" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">5</text>
      <title>Web min: 5</title>
    </g>
    <text x="128.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">Web</text>
    <line class="box-plot-whisker" x1="192.0" y1="155.56" x2="192.0" y2="137.78" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker" x1="192.0" y1="88.0" x2="192.0" y2="8.0" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker-cap" x1="183.0" y1="155.56" x2="201.0" y2="155.56" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <line class="box-plot-whisker-cap" x1="183.0" y1="8.0" x2="201.0" y2="8.0" stroke="var(--colour-text-muted)" stroke-width="1"/>
    <rect class="box-plot-box" x="174.0" y="88.0" width="36" height="49.78" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1">
      <title>Jobs: Q1 22.0, median 35.0, Q3 50.0, n=64</title>
    </rect>
    <line class="box-plot-median" x1="174.0" y1="114.67" x2="210.0" y2="114.67" stroke="var(--colour-brand)" stroke-width="1"/>
    <g class="box-plot-mark" data-box-mark="max">
      <circle class="box-plot-mark-hit" cx="192.0" cy="8.0" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="192.0" cy="8.0" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="216.0" y="11.0" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">95</text>
      <title>Jobs max: 95</title>
    </g>
    <g class="box-plot-mark" data-box-mark="q3">
      <circle class="box-plot-mark-hit" cx="192.0" cy="88.0" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="192.0" cy="88.0" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="216.0" y="91.0" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">50</text>
      <title>Jobs q3: 50</title>
    </g>
    <g class="box-plot-mark" data-box-mark="median">
      <circle class="box-plot-mark-hit" cx="192.0" cy="114.67" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="192.0" cy="114.67" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="216.0" y="117.67" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">35</text>
      <title>Jobs median: 35</title>
    </g>
    <g class="box-plot-mark" data-box-mark="q1">
      <circle class="box-plot-mark-hit" cx="192.0" cy="137.78" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="192.0" cy="137.78" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="216.0" y="140.78" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">22</text>
      <title>Jobs q1: 22</title>
    </g>
    <g class="box-plot-mark" data-box-mark="min">
      <circle class="box-plot-mark-hit" cx="192.0" cy="155.56" r="7" fill="transparent" stroke="none"/>
      <circle class="box-plot-mark-dot" cx="192.0" cy="155.56" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/>
      <text class="box-plot-mark-label" x="216.0" y="158.56" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">12</text>
      <title>Jobs min: 12</title>
    </g>
    <text x="192.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">Jobs</text>
  </svg>
  <p class="box-plot-summary">3 groups · 282 samples</p>
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
<div id="box-plot-root" data-dz-region>…</div>
```

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/box_plot.py`

- **Required root:** `[data-dz-box-plot]` (part `box-plot`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-box-plot]` | `data-dz-box-plot` | present (any value) |

#### Ingestion model `BoxPlotGroup`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `min` | `number` | no |
| `q1` | `number` | no |
| `median` | `number` | no |
| `q3` | `number` | no |
| `max` | `number` | no |
| `samples` | `integer` | no |

#### Exemplar `render()`

```python
def render(b: BoxPlot) -> str:
    """Model → box-plot region."""
    if not b.groups:
        return (
            f'<div class="dz-box-plot-region" data-dz-box-plot>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(b.empty_message)}</p>"
            f"</div>"
        )
    n_total = sum(g.samples for g in b.groups)
    summary = f'<p class="dz-box-plot-summary">{len(b.groups)} groups · {n_total} samples</p>'
    return f'<div class="dz-box-plot-region" data-dz-box-plot>{b.svg_html}{summary}</div>'
```

## Notes

Dual-lock root is data-dz-box-plot (contracts/box_plot.py). Schematic demo — real whisker/quartile geometry is server-computed via dazzle.render.svg.box_plot_svg and rides trusted svg_html. The summary line carries group count and sample total.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/box_plot.py`
