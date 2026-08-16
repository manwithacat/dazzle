# Date range (`date-range`)

Two native date inputs driving one htmx exchange — the from/to filter bar for time-scoped regions.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="date-range-picker date-range-bar" data-date-range>
  <label class="date-range-label" for="hm-dr-from">From</label>
  <span class="date-range-group"><input type="date" id="hm-dr-from" name="date_from" value="2026-06-01" class="date-range-input" hx-get="/mock/search" hx-target="#hm-dr-out" hx-swap="innerHTML" hx-include="closest .date-range-bar"><input data-date-iso class="date-range-iso" type="text" spellcheck="false" autocomplete="off" aria-label="From ISO date" value="2026-06-01"></span>
  <label class="date-range-label" for="hm-dr-to">To</label>
  <span class="date-range-group"><input type="date" id="hm-dr-to" name="date_to" value="2026-06-30" class="date-range-input" hx-get="/mock/search" hx-target="#hm-dr-out" hx-swap="innerHTML" hx-include="closest .date-range-bar"><input data-date-iso class="date-range-iso" type="text" spellcheck="false" autocomplete="off" aria-label="To ISO date" value="2026-06-30"></span>
  <div id="hm-dr-out" hidden></div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | Envelope | States |
|---|---|---|---|---|---|
| `GET /app/{region}?date_from=&date_to=` | either date input's change — hx-include sends both bounds | the re-rendered region body for the new range | innerHTML | `body_only` | — |

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Exchanges (swap · envelope)

- `GET /app/{region}?date_from=&date_to=` → innerHTML · **envelope=`body_only`**

### Replace / other HTML swap

- `GET /app/{region}?date_from=&date_to=` → body_only

### Envelope rules

- **`body_only`** — innerHTML / innerMorph into a slot; response is interior only (no re-wrap of slot id / nested `data-dz-region`).
- **`outer`** — outerHTML / outerMorph; response may carry identity.
- **`none`** — no HTML swap (JSON/204/bytes; client or OOB companion).
- **`host_owned`** — swap target/mode chosen by the host button's `hx-target` / `hx-swap` (part does not fix the envelope).
- **`document`** — full navigation / document load (not a fragment).
- Slot owns stable `id` / domain keys; state in DOM, not Alpine.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

#### `GET /app/{region}?date_from=&date_to=` · envelope=`body_only`

Correct response for body_only into #{region}-body (innerHTML / innerMorph). Wrong: re-wrapping the slot.

**Do — correct response body**

```html
<!-- envelope=body_only → re-rendered region body for the range -->
<div class="dz-stack" data-dz-gap="sm">
  <!-- metrics / rows for date_from..date_to -->
</div>
```

**Don’t — violates `body_only`**

```html
<!-- WRONG: date-range chrome re-emitted into the region body -->
<div id="{region}-body" data-dz-region>
  <input type="date" name="date_from" />
  <input type="date" name="date_to" />
</div>
```

## How to use it

### Seams

- root data-dz-date-range owns both native date inputs
- native type=date is the submitted value; [data-dz-date-iso] is the editable companion
- hx-include closest .date-range-bar sends both bounds on either change

### Do / Don't

| Do | Don't |
|---|---|
| write a valid companion ISO into the date; refuse leftover junk | POST From after To and let the server return an unexplained empty list |

### Pitfalls

- inverted From>To must not hx-get a silent empty region
- empty either bound is an open range — do not invent a missing date
- leftover ISO junk must not invent a bound (do not revert on blur)

### Keyboard / AT

- native type=date keeps the platform picker and constraint UI
- custom validity names the inversion so the bubble is not a generic required miss
- companion has aria-label; leftover junk fails custom validity

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/date_range.py`

- **Required root:** `[data-dz-date-range]` (part `date-range`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-date-range]` | `data-dz-date-range` | present (any value) |
| `[data-dz-date-iso]` | `data-dz-date-iso` | present (any value) |

#### Ingestion model `DateRange`

| Field | Type | Required |
|---|---|---|
| `region_name` | `string` | no |
| `endpoint` | `string` | no |
| `date_from` | `string` | no |
| `date_to` | `string` | no |
| `target` | `string` | no |
| `include_closed` | `string` | no |
| `as_of` | `string` | no |

#### Exemplar `render()`

```python
def render(d: DateRange) -> str:
    """Model → date-range picker bar."""
    rname = html.escape(d.region_name, quote=True)
    endpoint = html.escape(d.endpoint, quote=True)
    qs = _leftover_honest_temporal(
        getattr(d, "include_closed", ""),
        getattr(d, "as_of", ""),
    )
    if qs:
        endpoint = f"{endpoint}&amp;{qs}" if "?" in endpoint else f"{endpoint}?{qs}"
    target = html.escape(d.target or f"#region-{d.region_name}", quote=True)
    date_from = html.escape(d.date_from, quote=True)
    date_to = html.escape(d.date_to, quote=True)
    return (
        f'<div class="dz-date-range-picker date-range-bar" data-dz-date-range>'
        f"{_bound(rname, 'from', 'date_from', date_from, endpoint, target, 'From')}"
        f"{_bound(rname, 'to', 'date_to', date_to, endpoint, target, 'To')}"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-date-range (contracts/date_range.py). Native type="date" is the submitted value (ISO companion has no name). Each date input fires the region's hx-get on change and hx-include="closest .date-range-bar" sends BOTH bounds every time, so the server always sees the full range. dz-date-range.js blocks an inverted From>To change (custom validity + no silent empty-region GET). Leftover ISO junk must not invent a bound (cycle 2139).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/date_range.py`
- `controllers/dz-date-range.js`
