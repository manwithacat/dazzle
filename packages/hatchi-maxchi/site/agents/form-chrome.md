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

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Sections are real <section>s with an h3 title + optional note; fields inside use the HM form primitives. The error summary is role="alert" (the server re-renders it on a failed submit). The stepper here shows RENDERED states (is-active/is-not-last, aria-current="step") — the live navigation behaviour is the wizard Hyperpart (dz-wizard.js; the dzWizard Alpine island retired in Tier F4d).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
