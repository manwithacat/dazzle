# Confirm panel (`confirm-panel`)

The irreversible-action consent gate: a checklist of obligations that must be ticked before the primary action arms, plus live and revoked summary states.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="hm-measure">
  <div class="confirm-panel" data-state-value="off">
    <ul data-confirm-gate class="confirm-checklist" data-required-count="2">
      <li class="confirm-row" data-required="true">
        <input type="checkbox" class="confirm-checkbox" data-required="true" id="confirm-1">
        <label for="confirm-1" class="confirm-row-label"><span class="confirm-title">I have exported a backup of live data</span><span class="confirm-caption">Rollback needs a snapshot taken today.</span></label>
      </li>
      <li class="confirm-row" data-required="true">
        <input type="checkbox" class="confirm-checkbox" data-required="true" id="confirm-2">
        <label for="confirm-2" class="confirm-row-label"><span class="confirm-title">The billing owner has approved this change</span></label>
      </li>
      <li class="confirm-row" data-required="false">
        <input type="checkbox" class="confirm-checkbox" id="confirm-3">
        <label for="confirm-3" class="confirm-row-label"><span class="confirm-title">Notify the team afterwards (optional)</span></label>
      </li>
      <li class="confirm-actions"><a href="#" class="confirm-secondary">Save draft</a><a data-confirm-href="#go-live" aria-disabled="true" class="confirm-primary">Go live</a></li>
    </ul>
    <p class="confirm-audit">This action is recorded in the audit log with your identity and timestamp.</p>
  </div>
  <div class="confirm-panel" data-state-value="live">
    <div class="confirm-summary" data-confirm-tone="success">
      <div class="confirm-summary-title">Currently live</div>
      <div class="confirm-summary-body">Enabled 12 May by j.reyes.</div>
    </div>
    <div class="confirm-actions"><a href="#" class="confirm-revoke">Revoke</a></div>
  </div>
</div>
```

## Guidance (structured)

### Seams

- data-dz-confirm-gate root + data-dz-required=true checkboxes + data-dz-required-count
- primary anchor parks destination in data-dz-confirm-href until armed

### Pitfalls

- optional boxes never gate — only data-dz-required=true count
- zero required boxes means the gate is always armed

### Keyboard / AT

- primary stays aria-disabled until required count is met
- live/revoked branches use data-dz-confirm-tone for tone, not colour alone

### Do / Don't

| Do | Don't |
|---|---|
| keep armed state in the DOM (aria-disabled + href promotion) | mirror checked counts into a JS boolean a swap would orphan |

### Composes with

- `button` (agents/button.md)
- `field` (agents/field.md)

## Guidance (prose; HTML from the registry notes field)

The gate is state-in-DOM: the primary anchor ships with <code>aria-disabled=&quot;true&quot;</code> and its destination parked in <code>data-dz-confirm-href</code>; <code>dz-confirm-gate.js</code> recounts checked <code>data-dz-required=&quot;true&quot;</code> boxes on every change inside the <code>[data-dz-confirm-gate]</code> root and promotes the href / removes <code>aria-disabled</code> only when the count meets <code>data-dz-required-count</code>. Optional boxes never gate. Zero required boxes = always armed. The live and revoked branches swap the checklist for a <code>dz-confirm-summary</code> toned via <code>data-dz-confirm-tone=&quot;success|muted&quot;</code>.

## Controller files

- `controllers/dz-confirm-gate.js`
