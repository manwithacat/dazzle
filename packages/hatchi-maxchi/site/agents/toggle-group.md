# Toggle group (`toggle-group`)

Segmented control on native radios.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<fieldset class="toggle-group" role="radiogroup">
  <label><input type="radio" name="hm-view" checked><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-list"/></svg> List</span></label>
  <label><input type="radio" name="hm-view"><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-kanban"/></svg> Board</span></label>
  <label><input type="radio" name="hm-view"><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-calendar"/></svg> Calendar</span></label>
</fieldset>
```
