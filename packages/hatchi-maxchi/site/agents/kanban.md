# Kanban (`kanban`)

Status columns of cards — the flow view. Columns show a count; overflowing boards offer a server-rendered Load-all.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="kanban-board" role="region" aria-label="Kanban board" tabindex="0" data-kanban-board data-kanban-rearrange="status" data-kanban-status-field="status" data-kanban-api="/mock/kanban" data-kanban-src="/mock/kanban/board" data-kanban-rank-field="rank">
  <div class="kanban-announce" data-kanban-announce aria-live="polite" aria-atomic="true"></div>
  <div class="kanban-column">
    <div class="kanban-column-head"><span class="badge" data-tone="neutral">Open</span><span class="kanban-column-count">2</span></div>
    <div class="kanban-stack" data-kanban-stack data-to-state="open">
      <div class="kanban-card" data-kanban-card id="kanban-card-k1" data-entity-id="k1" data-from-state="open" data-rank="1000" data-allowed-to="in_progress done" draggable="true">
        <div class="kanban-card-body">
          <h4 class="kanban-card-title">Refund request — Acme</h4>
          <p class="kanban-card-field">£1,250 · assigned to Ada</p>
          <p class="kanban-card-attn" data-attn="critical">SLA breaches at 16:00</p>
          <div class="kanban-card-move">
            <label>
              <span class="visually-hidden">Move card</span>
              <select data-kanban-move aria-label="Move Refund request — Acme">
                <option value="">Move to…</option>
                <option value="in_progress">In Progress</option>
                <option value="done">Done</option>
              </select>
            </label>
          </div>
        </div>
      </div>
      <div class="kanban-card" data-kanban-card id="kanban-card-k2" data-entity-id="k2" data-from-state="open" data-rank="2000" data-allowed-to="in_progress" draggable="true">
        <div class="kanban-card-body">
          <h4 class="kanban-card-title">KYC review — Globex</h4>
          <p class="kanban-card-field">due tomorrow</p>
          <div class="kanban-card-move">
            <label>
              <span class="visually-hidden">Move card</span>
              <select data-kanban-move aria-label="Move KYC review — Globex">
                <option value="">Move to…</option>
                <option value="in_progress">In Progress</option>
              </select>
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="kanban-column">
    <div class="kanban-column-head"><span class="badge" data-tone="info">In progress</span><span class="kanban-column-count">1</span></div>
    <div class="kanban-stack" data-kanban-stack data-to-state="in_progress">
      <div class="kanban-card" data-kanban-card id="kanban-card-k3" data-entity-id="k3" data-from-state="in_progress" data-rank="1000" data-allowed-to="done open" draggable="true">
        <div class="kanban-card-body">
          <h4 class="kanban-card-title">Chargeback — Initech</h4>
          <p class="kanban-card-field">evidence uploaded</p>
          <div class="kanban-card-move">
            <label>
              <span class="visually-hidden">Move card</span>
              <select data-kanban-move aria-label="Move Chargeback — Initech">
                <option value="">Move to…</option>
                <option value="done">Done</option>
                <option value="open">Open</option>
              </select>
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="kanban-column">
    <div class="kanban-column-head"><span class="badge" data-tone="success"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>Done</span><span class="kanban-column-count">0</span></div>
    <div class="kanban-stack" data-kanban-stack data-to-state="done">
      <p class="kanban-empty">Nothing here yet.</p>
    </div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | Envelope | States |
|---|---|---|---|---|---|
| `PUT /api/{entity}/{id}` | dz-kanban.js: drag-drop onto a column stack or change `select[data-dz-kanban-move]` when the host stamped `data-dz-kanban-rearrange` (UPDATE only). Raw `fetch` PUT — not an htmx attribute on the card | this is the entity's STANDARD update route: JSON body includes the status field named by `data-dz-kanban-status-field` (e.g. `{"status": "in_progress"}`) and, when `data-dz-kanban-rank-field` is set, the rank key for in-column order (midpoint between neighbours). Server MUST re-validate SM edges and permissions — client `data-dz-allowed-to` is a hint. Return 2xx JSON on success; non-2xx aborts the optimistic move and the board reverts on the following GET refresh failure path | none (raw fetch) — controller then GETs `data-dz-kanban-src` to re-render the board from the server (same bulk-refresh pattern as grid PUT + `dz-grid:refresh`) | `none` | populated error |
| `GET /api/workspaces/{ws}/regions/{region}` | after a successful PUT move, `dz-kanban.js` fetches `data-dz-kanban-src` (the workspace region URL the host stamped). Also used when a host otherwise refreshes the region | the full kanban region fragment: root `[data-dz-kanban-board]` (or host region wrapper) with columns, stacks, and server-rendered cards (dual-lock `data-dz-kanban-card`). Counts and order come from the server — do not return a single card as the board settle. Empty columns keep the stack + empty state markup | outerMorph / outerHTML of the region root (or innerMorph of the board host if the host keeps a stable outer region shell). Prefer morph so announce live-region identity survives | `outer` | loading empty populated error |

### `PUT /api/{entity}/{id}` — example handler

Application code (not the dual-lock module). FastAPI-shaped; do not use `from __future__ import annotations` in route files (ADR-0014).

```python
# FastAPI sketch — product entity update (not a kanban-only API)
@router.put('/api/tickets/{ticket_id}')
async def update_ticket(
    ticket_id: str,
    body: TicketUpdate,  # status + optional rank fields
    user: User = Depends(current_user),
) -> TicketOut:
    # gate UPDATE; validate status transition (SM);
    # persist rank when present; return JSON entity
    ...
```

### `GET /api/workspaces/{ws}/regions/{region}` — example handler

Application code (not the dual-lock module). FastAPI-shaped; do not use `from __future__ import annotations` in route files (ADR-0014).

```python
# Region GET — same endpoint the workspace uses for the board
@router.get('/api/workspaces/{ws}/regions/{region}')
async def region_html(ws: str, region: str) -> HTMLResponse:
    # render SSR kanban board for current filters/persona
    return HTMLResponse(board_html)
```

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Exchanges (swap · envelope)

- `PUT /api/{entity}/{id}` → none (raw fetch) — controller then GETs `data-dz-kanban-src` to re-render the board from the server (same bulk-refresh pattern as grid PUT + `dz-grid:refresh`) · **envelope=`none`**
- `GET /api/workspaces/{ws}/regions/{region}` → outerMorph / outerHTML of the region root (or innerMorph of the board host if the host keeps a stable outer region shell). Prefer morph so announce live-region identity survives · **envelope=`outer`**

### Morph (persistent region)

- `GET /api/workspaces/{ws}/regions/{region}` → outer

### No HTML swap (raw fetch / companion OOB)

- `PUT /api/{entity}/{id}` → none

### Envelope rules

- **`body_only`** — innerHTML / innerMorph into a slot; response is interior only (no re-wrap of slot id / nested `data-dz-region`).
- **`outer`** — outerHTML / outerMorph; response may carry identity.
- **`none`** — no HTML swap (JSON/204/bytes; client or OOB companion).
- **`host_owned`** — swap target/mode chosen by the host button's `hx-target` / `hx-swap` (part does not fix the envelope).
- **`document`** — full navigation / document load (not a fragment).
- Slot owns stable `id` / domain keys; state in DOM, not Alpine.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

#### `PUT /api/{entity}/{id}` · envelope=`none`

Correct response for none (raw fetch / no HTML swap).

**Do — correct response body**

```text
// envelope=none — no HTML swap (JSON/204; client or OOB companion)
// HTTP 204 No Content
// or:
{ "ok": true }
// Application/json; status 200
// Optional: separate OOB HTML fragments if the host declares them
```

**Don’t — violates `none`**

```text
<!-- WRONG: HTML body when hx-swap is none / raw fetch expects JSON|204 -->
<div class="dz-alert">Deleted</div>
```

#### `GET /api/workspaces/{ws}/regions/{region}` · envelope=`outer`

Correct response for outer (outerHTML / outerMorph) replacing #slot.

**Do — correct response body**

```html
<!-- envelope=outer → response root may carry the slot identity -->
<div id="slot" class="dz-card" data-dz-card>
  <!-- full replacement of the previous element -->
</div>
```

**Don’t — violates `outer`**

```html
<!-- WRONG for outer: body-only fragment when the host expects a full element -->
<!-- (missing root that matches hx-target — leaves empty or nested junk) -->
<span>partial content without the target root</span>
```

## How to use it

### Seams

- rearrange: host stamps data-dz-kanban-rearrange=status only when UPDATE is permitted — never CSS-only drag
- per-card data-dz-allowed-to lists manual SM edges; empty = not draggable
- PUT entity update then GET data-dz-kanban-src (region refresh) — same bulk-refresh pattern as the grid
- keyboard: select[data-dz-kanban-move] offers the same targets as drag
- swap contract: PUT envelope=none (JSON); GET envelope=outer (full board/region fragment) — see Swap contract section

### Do / Don't

| Do | Don't |
|---|---|
| gate rearrange chrome on UPDATE like queue transitions | show grab cursors for everyone and 403 on drop |
| refresh the board from the region endpoint after PUT | optimistically reorder the DOM without a server settle |
| document PUT none + GET outer in the swap contract | leave Server exchange as n/a while the controller fetches |

### Pitfalls

- do not invent a second rearrange API — reuse entity UPDATE + SM validation
- do not stamp rearrange attrs for read-only personas (chrome leak)
- do not use dashboard personal-layout drag as the product model
- client allowed_to is a hint — server re-validates every drop
- do not return a single card HTML as the POST/PUT swap — settle via region GET
- do not claim presentation-only when rearrange attrs are stamped — declare the PUT+GET exchanges

### Keyboard / AT

- Move select is keyboard parity for drag
- aria-live announce region reports move result
- title hub drills stay clickable — drag starts off links/controls

### Related parts

- `queue` — agents/queue.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/kanban.py`

- **Required root:** `[data-dz-kanban-card]` (part `kanban`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-kanban-card]` | `data-dz-kanban-card` | present (any value) |

#### Ingestion model `KanbanCard`

| Field | Type | Required |
|---|---|---|
| `title` | `string` | yes |
| `fields_html` | `string` | no |
| `attention_level` | `string` | no |
| `attention_message` | `string` | no |
| `drill_url` | `string` | no |
| `row_id` | `string` | no |
| `from_state` | `string` | no |
| `allowed_to` | `array` | no |
| `rank` | `number | integer | string | null` | no |

#### Exemplar `render()`

```python
def render(card: KanbanCard) -> str:
    """Model → one kanban card."""
    title = html.escape(card.title)
    if card.drill_url:
        href = html.escape(card.drill_url, quote=True)
        # Keep h4 + class for dual-lock/CSS; wrap title text in hub drill
        # (queue-row pattern; empty drill_url stays byte-stable plain h4).
        title_html = (
            f'<h4 class="dz-kanban-card-title">'
            f'<a href="{href}" data-dz-kanban-drill>{title}</a>'
            f"</h4>"
        )
    else:
        title_html = f'<h4 class="dz-kanban-card-title">{title}</h4>'
    attn_html = ""
    if card.attention_level:
        level = html.escape(card.attention_level, quote=True)
        msg = html.escape(card.attention_message)
        attn_html = f'<p class="dz-kanban-card-attn" data-dz-attn="{level}">{msg}</p>'

    # Dual-lock root: always data-dz-kanban-card; rearrange attrs only when
    # host stamped capability (read-only boards stay presentation-only).
    root_bits = ["data-dz-kanban-card"]
    id_attr = ""
    if card.row_id:
        rid = html.escape(card.row_id, quote=True)
        root_bits.append(f'data-dz-entity-id="{rid}"')
        id_attr = f' id="dz-kanban-card-{rid}"'
    if card.from_state:
        root_bits.append(f'data-dz-from-state="{html.escape(card.from_state, quote=True)}"')
    if card.allowed_to:
        allowed = html.escape(" ".join(card.allowed_to), quote=True)
        root_bits.append(f'data-dz-allowed-to="{allowed}"')
    if card.rank is not None and card.rank != "":
        root_bits.append(f'data-dz-rank="{html.escape(str(card.rank), quote=True)}"')
    if card.row_id:
        root_bits.append('draggable="true"')
    root_attrs = " ".join(root_bits)

    return (
        f'<div class="dz-kanban-card" {root_attrs}{id_attr}>'
        f'<div class="dz-kanban-card-body">'
        f"{title_html}"
        f"{card.fields_html}"
        f"{attn_html}"
        f"{_move_select_html(card)}"
        f"</div>"
        f"</div>"
    )
```

## Notes

Cards are SERVER-rendered — dual-lock root is data-dz-kanban-card (contracts/kanban.py). Linear-class rearrange: when the host stamps data-dz-kanban-rearrange="status" (UPDATE only), dz-kanban.js moves cards via PUT (envelope none) then GET-refresh of data-dz-kanban-src with outerMorph/outerHTML of the region (prefer morph so the announce live-region identity survives); per-card data-dz-allowed-to lists legal edges. Read-only boards omit rearrange attrs entirely. Gallery /mock/kanban/* is demo-only. Attention text carries data-dz-attn (critical/warning/notice).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/kanban.py`
- `controllers/dz-kanban.js`
