# Toolbar (`toolbar`)

Inline composition — real button, toggle-group and menu markup nested in a role=toolbar bar. No client tree, no props: composition is HTML.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="toolbar" role="toolbar" aria-label="Editor actions">
  <button class="button" data-variant="primary"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-circle-plus"/></svg> New</button>
  <div class="toggle-group" role="radiogroup" aria-label="View">
    <label><input type="radio" name="tb-view" checked><span>List</span></label>
    <label><input type="radio" name="tb-view"><span>Grid</span></label>
  </div>
  <details class="menu">
    <summary class="button" data-variant="outline">More ▾</summary>
    <div class="menu__panel"><button class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-copy"/></svg> Duplicate</button><button class="menu__item" data-tone="destructive"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-trash-2"/></svg> Delete</button></div>
  </details>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The dependency chips aggregate what the children need (here: Sprite, from the menu/button icons). Copy the whole thing — it is just nested markup.
