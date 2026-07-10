# Wizard (`wizard`)

Multi-stage form navigation: the stepper drives stage reveal — back freely, forward one validated step at a time.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

State-in-DOM: the root's <code>data-dz-step</code> is the current stage; stages toggle via the native <code>hidden</code> attribute; stepper items carry <code>data-dz-state=&quot;complete|current|pending&quot;</code> (the checkmark is pure CSS off the state). <code>dz-wizard.js</code> allows going BACK freely and FORWARD one step at a time — only after every required input in the current stage passes <code>reportValidity()</code>. No-JS renders stage one with numbered steps (the form still posts whole).

## Controller files

- `controllers/dz-wizard.js`
