# Command palette (`command`)

The hx-get palette — the htmx4 flagship. Press ⌘K.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<button class="button" data-variant="outline" data-hm-open-command>Open palette <kbd class="kbd">⌘K</kbd></button>
<dialog class="command" aria-label="Command palette" closedby="any">
  <div class="command__bar"><input class="command__input" type="search" placeholder="Search workspaces and records…" aria-controls="command-results" aria-autocomplete="list" hx-get="/mock/command" hx-trigger="input changed delay:150ms, focus once" hx-target="next .command__results"><button type="button" class="command__close" data-hm-close-command aria-label="Close command palette"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></div>
  <div class="command__results" id="command-results" role="listbox" aria-label="Results"></div>
</dialog>
```

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/command` | the search input, on `input` (debounced 150ms) and first `focus` | zero or more result rows — `<a>`/`<button class="dz-command__item" role="option">` grouped by `<div class="dz-command__group">` headers; empty query or no matches returns `<div class="dz-command__empty">` | innerHTML of the sibling `.dz-command__results` listbox | loading empty populated error |

## Guidance (prose; HTML from the registry notes field)

In Dazzle the input's hx-get hits <code>/app/command</code>, which returns persona-scoped results. Here a mock htmx returns a canned list so the demo works with no server.

## Controller files

- `controllers/dz-command.js`
