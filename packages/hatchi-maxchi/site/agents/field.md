# Field (`field`)

The label + control + help + error triad as one accessible unit. Error state derives from aria-invalid; help/error bind via aria-describedby.

> **Layer:** L1 surface · **Recipe:** `field-triad` — label + help + error triad
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack hm-measure">
  <div class="form-field">
    <label class="form-label" for="hm-field-email">Billing email<span class="form-required">*</span></label>
    <input class="form-input" id="hm-field-email" type="email" required placeholder="you@company.com" aria-describedby="hm-field-email-hint">
    <p class="form-hint" id="hm-field-email-hint">Receipts and renewal notices go here.</p>
  </div>
  <div class="form-field">
    <label class="form-label" for="hm-field-slug">Workspace slug</label>
    <input class="form-input" id="hm-field-slug" value="Acme Corp" aria-invalid="true" aria-describedby="hm-field-slug-error">
    <p class="form-error" id="hm-field-slug-error">Use lowercase letters, numbers and hyphens only.</p>
  </div>
  <div class="form-field">
    <label class="form-label" for="hm-field-color">Brand colour</label>
    <div class="form-color-group" data-color-group><input class="form-color-input" id="hm-field-color" type="color" value="#3b82f6"><span class="form-color-hex">#3b82f6</span></div>
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

### `contracts/color.py`

- **Required root:** `[data-dz-color-group]` (part `color`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-color-group]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: field (extension: dz-color) — colour input group."""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="color",
    root="[data-dz-color-group]",
    nodes=(Node("[data-dz-color-group]", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Reuses the dz-form-* family (label / hint / input / error). The invalid field needs no modifier class — the red border keys off aria-invalid="true", the same attribute assistive tech reads. The colour group uses data-dz-color-group so dz-color.js can mirror the swatch into the hex readout (contract: contracts/color.py).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/color.py`
