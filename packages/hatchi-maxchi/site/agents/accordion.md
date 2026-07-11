# Accordion (`accordion`)

Native <details> group; single-open via the HTML name= attribute — opening one closes its siblings, zero JS.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="accordion">
  <details class="accordion__item" name="hm-acc" open>
    <summary class="accordion__trigger">What is a Hyperpart?</summary>
    <div class="accordion__panel">A server-rendered partial plus its exchange contract — the htmx-native unit of reuse.</div>
  </details>
  <details class="accordion__item" name="hm-acc">
    <summary class="accordion__trigger">Do I need a client framework?</summary>
    <div class="accordion__panel">No — state lives on the server and htmx swaps the markup.</div>
  </details>
  <details class="accordion__item" name="hm-acc">
    <summary class="accordion__trigger">Can two panels be open at once?</summary>
    <div class="accordion__panel">Not while they share a name=. Drop the attribute for an independent, multi-open group.</div>
  </details>
</div>
```

## Notes

Exclusivity is the native name attribute on <details> — the browser closes the open sibling for you. No aria-expanded wiring: <details>/<summary> carry it.
