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

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

**No host HTMX exchange** on this part — presentation or client chrome only. **Exchange envelope:** `n/a`.

If a **host** wraps this markup in `hx-*`, **that host owns the swap contract** (sole identity + envelope). Prefer `innerMorph` / `outerMorph` for stable slots; replacement for flash; body-only responses under inner swaps.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

This part has no owned exchange (envelope `n/a`). If a host adds `hx-*`, that host’s envelope applies — typically `body_only`:

```html
<!-- Prefer hx-swap=innerMorph into a stable body slot -->
<div class="dz-stack">content…</div>
```

Do **not** re-own the slot:

```html
<div id="kanban-root" data-dz-region>…</div>
```

## How to use it

### Seams

- rearrange: host stamps data-dz-kanban-rearrange=status only when UPDATE is permitted — never CSS-only drag
- per-card data-dz-allowed-to lists manual SM edges; empty = not draggable
- PUT entity update then GET data-dz-kanban-src (region refresh) — same bulk-refresh pattern as the grid
- keyboard: select[data-dz-kanban-move] offers the same targets as drag

### Do / Don't

| Do | Don't |
|---|---|
| gate rearrange chrome on UPDATE like queue transitions | show grab cursors for everyone and 403 on drop |
| refresh the board from the region endpoint after PUT | optimistically reorder the DOM without a server settle |

### Pitfalls

- do not invent a second rearrange API — reuse entity UPDATE + SM validation
- do not stamp rearrange attrs for read-only personas (chrome leak)
- do not use dashboard personal-layout drag as the product model
- client allowed_to is a hint — server re-validates every drop

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

Cards are SERVER-rendered — dual-lock root is data-dz-kanban-card (contracts/kanban.py). Linear-class rearrange: when the host stamps data-dz-kanban-rearrange="status" (UPDATE only), dz-kanban.js moves cards via PUT + region refresh; per-card data-dz-allowed-to lists legal edges. Read-only boards omit rearrange attrs entirely. Gallery /mock/kanban/* is demo-only. Attention text carries data-dz-attn (critical/warning/notice).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/kanban.py`
- `controllers/dz-kanban.js`
