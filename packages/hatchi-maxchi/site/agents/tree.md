# Tree (`tree`)

Hierarchy on native <details>/<summary> for branches; leaves are plain rows. Chevron is CSS chrome (not summary content). No JS.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-measure">
  <div class="tree" data-tree>
    <details class="tree-node" open>
      <summary class="tree-summary"><span class="tree-label">Engineering</span><span class="tree-count">2</span></summary>
      <div class="tree-children">
        <details class="tree-node">
          <summary class="tree-summary"><span class="tree-label">Platform</span><span class="tree-count">1</span></summary>
          <div class="tree-children">
            <div class="tree-leaf"><span class="tree-label">Build tooling</span></div>
          </div>
        </details>
        <details class="tree-node">
          <summary class="tree-summary"><span class="tree-label">Design systems</span><span class="tree-count">1</span></summary>
          <div class="tree-children">
            <div class="tree-leaf"><span class="tree-label">Tokens</span></div>
          </div>
        </details>
      </div>
    </details>
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
<div id="tree-root" data-dz-region>…</div>
```

## How to use it

### Seams

- `[data-dz-tree]` / `.dz-tree` forest root (dual-lock)
- `details.dz-tree-node` + `summary.dz-tree-summary` for branches (label + count only; chevron is CSS)
- `.dz-tree-leaf` for nodes with no children

### Do / Don't

| Do | Don't |
|---|---|
| Leave multi-open native details for sibling branches; emit leaves as .dz-tree-leaf | Port dz-menubar exclusive-open onto the tree forest; or put chevron markup in every summary |

### Pitfalls

- Do not put chevron SVG/span in the summary — disclosure chrome belongs in CSS (::before on branches)
- Do not wrap leaves in empty <details> — that still shows a rotating arrow UX with nothing to expand
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

Open intent: multi_open (stem details-open-intent) — sibling branches stay open; do not add exclusive-open. Dual-lock root data-dz-tree (contracts/tree.py). Summary holds content (label + count); the rotating chevron is CSS ::before on .dz-tree-node:has(> .dz-tree-children) — never an SVG/span in the summary. Leaves are .dz-tree-leaf (no expand affordance). Count chip only when children exist. Gallery probe tree.multi_open (scope .hm-preview).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/tree.py`
