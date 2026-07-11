# Slider (`slider`)

Native <input type=range> — styled track + thumb, both themes, with a live value readout via a tiny delegated controller.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="hm-stack hm-measure">
  <label class="form-label" for="hm-slider-vol">Volume</label>
  <div class="form-slider-group"><input id="hm-slider-vol" type="range" data-slider class="form-slider" min="0" max="100" step="1" value="70"><span data-range-value class="form-slider-value" aria-hidden="true">70</span></div>
</div>
```

## How to use it

### Seams

- native <input type=range> is the value source; [data-dz-range-value] is the readout
- each slider group is scoped so many coexist on one page

### Do / Don't

| Do | Don't |
|---|---|
| write the live value into [data-dz-range-value] on input | replace the native range with a div-based slider |

### Pitfalls

- the visible readout is aria-hidden — the range already announces to AT
- do not invent a custom thumb/track in JS; style the native control

### Keyboard / AT

- Arrow keys adjust the native range (browser default)
- focus ring is theme-aware on the track/thumb

### Related parts

- `field` — agents/field.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/slider.py`

- **Required root:** `[data-dz-slider]` (part `slider`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-slider]` | `—` | — |
| `[data-dz-range-value]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: slider — native range group + live value readout."""


from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="slider",
    root="[data-dz-slider]",
    nodes=(
        Node("[data-dz-slider]", attrs={}),
        Node("[data-dz-range-value]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

The track + thumb are styled for both themes with a focus ring; the native range already announces its value to assistive tech, so the visible readout is aria-hidden. dz-slider.js writes the value into [data-dz-range-value] on input, scoped to each slider's own group so many coexist.

## Source files

- `controllers/dz-slider.js`
