# Accordion (`accordion`)

Native <details> group; single-open via the HTML name= attribute — opening one closes its siblings, zero JS.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

Exclusivity is the native <code>name</code> attribute on <code>&lt;details&gt;</code> — the browser closes the open sibling for you. No <code>aria-expanded</code> wiring: <code>&lt;details&gt;/&lt;summary&gt;</code> carry it.
