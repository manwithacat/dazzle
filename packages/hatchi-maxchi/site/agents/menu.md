# Menu (`menu`)

Disclosure menu (`<details>`) — no JS for open state. A disclosure, not a full ARIA menu: no roving tabindex or typeahead.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<details class="menu">
  <summary class="button" data-variant="outline">Actions ▾</summary>
  <div class="menu__panel">
    <button class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-pencil"/></svg> Edit</button>
    <button class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-copy"/></svg> Duplicate</button>
    <hr class="menu__separator">
    <button class="menu__item" data-tone="destructive"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-trash-2"/></svg> Delete</button>
  </div>
</details>
```
