# Dialog (`dialog`)

Modal on the native <dialog> — one line of JS to open, close for free (Esc / backdrop / method=dialog submit). Focus-trapped by the platform.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<button class="button" data-variant="primary" data-dialog-open="hm-dialog-demo">Delete workspace…</button>
<dialog class="dialog" id="hm-dialog-demo" aria-labelledby="hm-dialog-demo-title" closedby="any">
  <form method="dialog">
    <div class="dialog__header">
      <h2 class="dialog__title" id="hm-dialog-demo-title">Delete workspace?</h2>
      <button type="submit" class="dialog__close" aria-label="Close dialog"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>
    <div class="dialog__body">
      <p>This permanently deletes the workspace and every record in it. This action cannot be undone.</p>
    </div>
    <div class="dialog__footer"><button type="submit" class="button" data-variant="outline">Cancel</button><button type="submit" class="button" data-variant="destructive" value="confirm">Delete</button></div>
  </form>
</dialog>
```

## Guidance (prose; HTML from the registry notes field)

Opening is the only scripted behaviour (<code>dz-dialog.js</code> calls <code>showModal()</code> for a <code>[data-dz-dialog-open]</code> trigger); closing is native. The confirm button closes the dialog and sets <code>returnValue</code> — in a real app, carry the action on it (<code>hx-delete</code> …) or submit a form to the server.

## Controller files

- `controllers/dz-dialog.js`
