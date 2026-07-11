# Wizard (`wizard`)

Multi-stage form navigation: the stepper drives stage reveal — back freely, forward one validated step at a time.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div data-wizard data-step="0" class="hm-measure-lg">
  <ol class="form-stepper" role="list" aria-label="Form progress">
    <li class="form-stepper-item is-not-last" data-state="current" aria-current="step"><button type="button" class="form-stepper-button" data-step-to="0"><span class="form-stepper-circle is-active"><span>1</span></span><span class="form-stepper-label is-active">Details</span><span class="visually-hidden" data-step-status>current</span></button><span class="form-stepper-connector" aria-hidden="true"></span></li>
    <li class="form-stepper-item is-not-last" data-state="pending"><button type="button" class="form-stepper-button" data-step-to="1"><span class="form-stepper-circle"><span>2</span></span><span class="form-stepper-label">Schedule</span><span class="visually-hidden" data-step-status>pending</span></button><span class="form-stepper-connector" aria-hidden="true"></span></li>
    <li class="form-stepper-item" data-state="pending"><button type="button" class="form-stepper-button" data-step-to="2"><span class="form-stepper-circle"><span>3</span></span><span class="form-stepper-label">Review</span><span class="visually-hidden" data-step-status>pending</span></button></li>
  </ol>
  <div class="wizard-stage" data-stage="0">
    <div class="form-field">
      <label class="form-label" for="hm-wiz-name">Project name<span class="form-required" aria-hidden="true">*</span></label>
      <input id="hm-wiz-name" class="form-input" type="text" required aria-required="true">
    </div>
  </div>
  <div class="wizard-stage" data-stage="1" hidden>
    <div class="form-field">
      <label class="form-label" for="hm-wiz-date">Start date</label>
      <input id="hm-wiz-date" class="form-input" type="date">
    </div>
  </div>
  <div class="wizard-stage" data-stage="2" hidden>
    <p>Review your answers, then submit.</p>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- root data-dz-step is the current stage; stages use native hidden
- stepper items carry data-dz-state=complete|current|pending (CSS checkmark)

### Do / Don't

| Do | Don't |
|---|---|
| keep stage index in data-dz-step on the wizard root | store step in a JS variable a morph would discard |

### Pitfalls

- forward only after reportValidity() on the current stage's required inputs
- no-JS still posts the whole form — stage one is the visible path

### Keyboard / AT

- Back is always free; Forward is one step and validity-gated
- invalid inputs receive focus so the browser validity bubble appears

### Related parts

- `field` — agents/field.md
- `button` — agents/button.md
- `progress` — agents/progress.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/wizard.py`

- **Required root:** `[data-dz-wizard]` (part `wizard`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-wizard]` | `data-dz-step` | present (any value) |
| `[data-dz-stage]` | `data-dz-stage` | present (any value) |
| `[data-dz-state]` | `data-dz-state` | one of ['complete', 'current', 'pending'] |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: wizard — multi-stage form with data-dz-step state."""

from contracts._kit import DomContract, Node, OneOf, Present

DOM_CONTRACT = DomContract(
    part="wizard",
    root="[data-dz-wizard]",
    nodes=(
        Node("[data-dz-wizard]", attrs={"data-dz-step": Present()}),
        Node("[data-dz-stage]", attrs={"data-dz-stage": Present()}),
        Node(
            "[data-dz-state]",
            attrs={"data-dz-state": OneOf("complete", "current", "pending")},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

State-in-DOM: the root's data-dz-step is the current stage; stages toggle via the native hidden attribute; stepper items carry data-dz-state="complete|current|pending" (the checkmark is pure CSS off the state). dz-wizard.js allows going BACK freely and FORWARD one step at a time — only after every required input in the current stage passes reportValidity(). No-JS renders stage one with numbered steps (the form still posts whole).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/wizard.py`
- `controllers/dz-wizard.js`
