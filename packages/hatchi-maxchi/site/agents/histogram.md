# Histogram (`histogram`)

Value-distribution buckets as a server-rendered SVG plus a mono summary line.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="histogram-region hm-measure-lg" data-histogram>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" role="img" aria-label="Histogram — 6 buckets, 120 samples"><rect x="4" y="30" width="24" height="18" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="32" y="18" width="24" height="30" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="60" y="6" width="24" height="42" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="88" y="14" width="24" height="34" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="116" y="28" width="24" height="20" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="144" y="38" width="24" height="10" fill="var(--colour-brand)" fill-opacity="0.7"/></svg>
  <p class="histogram-summary">6 buckets · 120 samples</p>
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

### `contracts/histogram.py`

- **Required root:** `[data-dz-histogram]` (part `histogram`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-histogram]` | `data-dz-histogram` | present (any value) |

#### Ingestion model `HistogramBin`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `count` | `integer` | no |
| `low` | `number` | no |
| `high` | `number` | no |

#### Exemplar `render()`

```python
def render(h: Histogram) -> str:
    """Model → histogram region."""
    if not h.bins:
        return (
            f'<div class="dz-histogram-region" data-dz-histogram>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(h.empty_message)}</p>"
            f"</div>"
        )
    total = sum(b.count for b in h.bins)
    max_count = max(b.count for b in h.bins) or 1
    summary = (
        f'<p class="dz-histogram-summary">'
        f"{len(h.bins)} bins · {total} samples · peak {max_count}"
        f"</p>"
    )
    return f'<div class="dz-histogram-region" data-dz-histogram>{h.svg_html}{summary}</div>'
```

## Notes

Dual-lock root is data-dz-histogram (contracts/histogram.py). The SVG body is SERVER-computed (this demo is schematic — the real geometry comes from dazzle.render.svg.histogram_svg) with the numeric story in aria-label and the mono summary line. Bin geometry rides trusted svg_html so HM need not import Dazzle SVG helpers.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/histogram.py`
