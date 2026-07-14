# Form chrome (`form-chrome`)

The structural form pieces: titled sections, the validation-error summary, and the multi-section progress stepper.

> **Layer:** L2 host · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack hm-measure">
  <div class="form-errors" role="alert">
    <svg class="form-errors-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
    <div class="form-errors-body">
      <h3 class="form-errors-title">Validation Error</h3>
      <ul class="form-errors-list" role="list">
        <li>Name is required</li>
        <li>Start date must be before end date</li>
      </ul>
    </div>
  </div>
  <ol class="form-stepper" role="list" aria-label="Form progress">
    <li class="form-stepper-item is-not-last" aria-current="step"><span class="form-stepper-circle is-active"><span>1</span></span><span class="form-stepper-label is-active">Details</span><span class="form-stepper-connector" aria-hidden="true"></span></li>
    <li class="form-stepper-item is-not-last"><span class="form-stepper-circle"><span>2</span></span><span class="form-stepper-label">Schedule</span><span class="form-stepper-connector" aria-hidden="true"></span></li>
    <li class="form-stepper-item"><span class="form-stepper-circle"><span>3</span></span><span class="form-stepper-label">Review</span></li>
  </ol>
  <section class="form-section">
    <h3 class="form-section-title">Contact details</h3>
    <p class="form-section-note">Shown on invoices and receipts.</p>
    <div class="form-field">
      <label class="form-label" for="hm-fc-name">Full name<span class="form-required" aria-hidden="true">*</span></label>
      <input id="hm-fc-name" class="form-input" type="text" aria-required="true">
    </div>
  </section>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

This L2 host has no declared hypermedia exchanges in the registry. If you add persistent region updates, prefer `innerMorph` / `outerMorph` with stable row/panel ids; use replacement for flash panes and full resets.

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/form_errors.py`

- **Required root:** `.dz-form-errors` (part `form_errors`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-form-errors` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: form_errors — form-level validation error summary.

Dual-lock unit is the errors root. Title, list items, and icon are
host-owned. Class ``.dz-form-errors`` is the stable substrate root
(form-chrome CSS; no FragmentRenderer emit yet — server re-renders on
failed submit).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form_errors",
    root=".dz-form-errors",
    nodes=(Node(".dz-form-errors", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

### `contracts/form_stepper.py`

- **Required root:** `.dz-form-stepper` (part `form-stepper`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-form-stepper` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: form-stepper — multi-step form progress list.

Dual-lock unit is the stepper root. Step labels, state attrs, and wizard
controller seams are host-owned. Class ``.dz-form-stepper`` is the stable
substrate root (``_emit_form_stepper``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form-stepper",
    root=".dz-form-stepper",
    nodes=(Node(".dz-form-stepper", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

### `contracts/form_section.py`

- **Required root:** `.dz-form-section` (part `form-section`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-form-section` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: form-section — labelled field group inside a form stack.

Dual-lock unit is the section root. Title, note, and nested fields are
host-owned. Class ``.dz-form-section`` is the stable substrate root
(``_emit_form_section``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form-section",
    root=".dz-form-section",
    nodes=(Node(".dz-form-section", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

### `contracts/form_field.py`

- **Required root:** `.dz-form-field` (part `form-field`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-form-field` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: form-field — plain form field wrapper.

Dual-lock unit is the field root. Label, input, help, and a11y attrs are
host-owned. Class ``.dz-form-field`` is the stable substrate root
(``_emit_field``). Distinct from specialized widgets (combobox/tags/…).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form-field",
    root=".dz-form-field",
    nodes=(Node(".dz-form-field", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Sections are real <section>s with an h3 title + optional note; fields inside use the HM form primitives. The error summary is role="alert" (the server re-renders it on a failed submit). The stepper here shows RENDERED states (is-active/is-not-last, aria-current="step") — the live navigation behaviour is the wizard Hyperpart (dz-wizard.js; the dzWizard Alpine island retired in Tier F4d). Dual-lock: form_errors + form_stepper + form_section + form_field (HMC-143).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/form_errors.py`
- `contracts/form_stepper.py`
- `contracts/form_section.py`
- `contracts/form_field.py`
