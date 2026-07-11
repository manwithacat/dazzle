# Master–detail (`master-detail`)

Exchange composition — a list item hx-gets its detail card into the detail pane. The canonical htmx composite; two can coexist on a page.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="master-detail" data-master-detail>
  <ul class="master-detail__list" aria-label="Invoices" data-master-detail-list-body>
    <li><a class="master-detail__item" href="#" aria-current="true" hx-get="/mock/master-detail/inv-001" hx-target="next .master-detail__detail">INV-001 · Acme</a></li>
    <li><a class="master-detail__item" href="#" hx-get="/mock/master-detail/inv-002" hx-target="next .master-detail__detail">INV-002 · Globex</a></li>
    <li><a class="master-detail__item" href="#" hx-get="/mock/master-detail/inv-003" hx-target="next .master-detail__detail">INV-003 · Initech</a></li>
  </ul>
  <div class="master-detail__detail" data-master-detail-detail-body>
    <div class="card card-body">
      <div class="card-label">INV-001 · Acme</div>
      <div class="card-value">£1,250.00</div>
      <div class="card-delta">Paid · 2 days ago</div>
    </div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the HTML fragment described (not gallery mock toasts). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/master-detail/{id}` | a list item, on click | a detail card fragment — `<div class="dz-card dz-card-body">…` | innerHTML of the sibling `.dz-master-detail__detail` pane | loading populated error |

## How to use it

### Seams

- detail pane loads a card fragment via hx-get from the selected item
- aria-current marks the chosen list item, scoped to THIS root

### Do / Don't

| Do | Don't |
|---|---|
| hx-get the detail card into the detail pane on item activate | stash all detail payloads in data-* attributes on every list row |

### Pitfalls

- two master-detail roots must not share aria-current — controller is per-root
- detail content is a server fragment, not a client template

### Keyboard / AT

- aria-current=true on the active list item
- list items remain keyboard-activatable links/buttons

### Related parts

- `card` — agents/card.md
- `list-region` — agents/list-region.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/master_detail.py`

- **Required root:** `[data-dz-master-detail]` (part `master-detail`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-master-detail]` | `—` | — |
| `[data-dz-master-detail-list-body]` | `—` | — |
| `[data-dz-master-detail-detail-body]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: master-detail — selection marker + detail pane root.

Dazzle emission site (workspace dual_pane_flow LIST+DETAIL pair):
``dazzle.page.runtime.dual_pane_master_detail.render_master_detail_shell``.
List rows carry ``.dz-master-detail__item`` and hx-get a detail fragment into
``.dz-master-detail__detail``; ``dz-master-detail.js`` owns aria-current.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="master-detail",
    root="[data-dz-master-detail]",
    nodes=(
        Node("[data-dz-master-detail]", attrs={}),
        # Pane markers (kit selectors are [attr] only — no class engine).
        Node("[data-dz-master-detail-list-body]", attrs={}),
        Node("[data-dz-master-detail-detail-body]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

The detail pane loads a card fragment via hx-get; dz-master-detail.js sets aria-current on the chosen item, scoped to THIS root so two coexist.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/master_detail.py`
- `controllers/dz-master-detail.js`
