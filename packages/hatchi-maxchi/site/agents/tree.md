# Tree (`tree`)

Hierarchy on native <details>/<summary> — indented children, rotating chevron, child-count chips. No JS at all.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-measure">
  <div class="tree" data-tree>
    <details class="tree-node" open>
      <summary class="tree-summary"><svg class="tree-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg><span class="tree-label">Engineering</span><span class="tree-count">2</span></summary>
      <div class="tree-children">
        <details class="tree-node">
          <summary class="tree-summary"><svg class="tree-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg><span class="tree-label">Platform</span><span class="tree-count">1</span></summary>
          <div class="tree-children">
            <details class="tree-node">
              <summary class="tree-summary"><svg class="tree-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg><span class="tree-label">Build tooling</span></summary>
            </details>
          </div>
        </details>
        <details class="tree-node">
          <summary class="tree-summary"><svg class="tree-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg><span class="tree-label">Design systems</span></summary>
        </details>
      </div>
    </details>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `[data-dz-tree]` / `.dz-tree` forest root (dual-lock)
- `details.dz-tree-node` + `summary.dz-tree-summary` per node

### Do / Don't

| Do | Don't |
|---|---|
| Leave multi-open native details for sibling branches | Port dz-menubar exclusive-open onto the tree forest |

### Pitfalls

- Do not ship exclusive-open or name= exclusivity on tree peers
- Gallery may mount a second forest under .hm-contract-live__preview — interaction checks use .hm-preview only
- Not menubar/nav chrome — no outside-dismiss controller

### Keyboard / AT

- Native details/summary expand/collapse
- Keyboard: Enter/Space on summary

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/tree.py`

- **Required root:** `[data-dz-tree]` (part `tree`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-tree]` | `data-dz-tree` | present (any value) |

#### Ingestion model `Tree`

| Field | Type | Required |
|---|---|---|
| `body_html` | `string` | no |

#### Exemplar `render()`

```python
def render(t: Tree) -> str:
    """Model → tree region root."""
    return f'<div class="dz-tree" data-dz-tree>{t.body_html}</div>'
```

## Notes

Open intent: multi_open (stem details-open-intent) — sibling branches stay open; do not add exclusive-open. Dual-lock root data-dz-tree (contracts/tree.py). Pure hypermedia: state is the native open attribute; chevron keys off .dz-tree-node[open]; levels indent via dz-tree-children. Depth-0 nodes default open; count chip only when children exist. Gallery probe tree.multi_open (scope .hm-preview).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/tree.py`
