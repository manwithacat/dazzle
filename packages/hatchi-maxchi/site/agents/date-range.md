# Date range (`date-range`)

Two native date inputs driving one htmx exchange — the from/to filter bar for time-scoped regions.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="date-range-picker date-range-bar">
  <label class="date-range-label" for="hm-dr-from">From</label>
  <input type="date" id="hm-dr-from" name="date_from" value="2026-06-01" class="date-range-input" hx-get="/mock/search" hx-target="#hm-dr-out" hx-swap="innerHTML" hx-include="closest .date-range-bar">
  <label class="date-range-label" for="hm-dr-to">To</label>
  <input type="date" id="hm-dr-to" name="date_to" value="2026-06-30" class="date-range-input" hx-get="/mock/search" hx-target="#hm-dr-out" hx-swap="innerHTML" hx-include="closest .date-range-bar">
  <div id="hm-dr-out" hidden></div>
</div>
```

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}?date_from=&date_to=` | either date input's change — hx-include sends both bounds | the re-rendered region body for the new range | innerHTML | — |

## Guidance (prose; HTML from the registry notes field)

Native <code>type=&quot;date&quot;</code> inputs — no picker JS. Each input fires the region's hx-get on change and <code>hx-include=&quot;closest .date-range-bar&quot;</code> sends BOTH bounds every time, so the server always sees the full range.
