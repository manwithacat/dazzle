# Confirm dialog (`confirm`)

Designed replacement for window.confirm — every hx-confirm upgrades automatically.

## Partial (copy-paste; the live demo renders this exact string)

```html
<button class="button" data-variant="destructive" hx-delete="/mock/noop" hx-confirm="Delete this invoice? This cannot be undone.">Delete invoice</button>
```

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `DELETE /app/invoices/{id}` | the button, after the user approves the designed confirm dialog | the server deletes the resource and returns the replacement markup for the affected region (e.g. the row's removal, or an empty-state) | per the button's `hx-target`/`hx-swap` (row removal by default) | — |

## Guidance (prose; HTML from the registry notes field)

dz-confirm.js intercepts <code>htmx:confirm</code> (a client affordance — no server round-trip). On approval it issues the underlying request. No per-button wiring — any element with <code>hx-confirm</code> gets the designed dialog.

## Controller files

- `controllers/dz-confirm.js`
