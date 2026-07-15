# Diagram (`diagram`)

A horizontal-scroll wrapper for server-emitted Mermaid source — the library replaces the <pre> with rendered SVG.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="diagram-scroll" data-diagram>
  <pre class="mermaid diagram-source">erDiagram
  CUSTOMER ||--o{ ORDER : places
  ORDER ||--|{ LINE_ITEM : contains</pre>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/diagram.py`

- **Required root:** `[data-dz-diagram]` (part `diagram`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-diagram]` | `data-dz-diagram` | present (any value) |

#### Ingestion model `Diagram`

| Field | Type | Required |
|---|---|---|
| `mermaid_source` | `string` | no |
| `nodes` | `array` | no |
| `edges` | `array` | no |

#### Exemplar `render()`

```python
def render(d: Diagram) -> str:
    """Model → diagram root (Mermaid shell or structural list)."""
    if d.mermaid_source:
        src = html.escape(d.mermaid_source)
        return (
            f'<div class="dz-diagram-scroll" data-dz-diagram>'
            f'<pre class="mermaid dz-diagram-source">{src}</pre>'
            f"</div>"
        )
    nodes_html = "".join(
        f'<li class="dz-diagram__node" data-dz-key="{html.escape(name, quote=True)}">'
        f"{html.escape(name)}</li>"
        for name in d.nodes
    )
    edges_html = "".join(
        f'<li class="dz-diagram__edge">'
        f'<span class="dz-diagram__edge-from">{html.escape(src)}</span>'
        f'<span class="dz-diagram__edge-arrow">→</span>'
        f'<span class="dz-diagram__edge-to">{html.escape(dst)}</span>'
        f"</li>"
        for src, dst in d.edges
    )
    return (
        f'<section class="dz-diagram" data-dz-diagram>'
        f'<ul class="dz-diagram__nodes">{nodes_html}</ul>'
        f'<ul class="dz-diagram__edges">{edges_html}</ul>'
        f"</section>"
    )
```

## Notes

Dual-lock root is data-dz-diagram (contracts/diagram.py). The gallery part page loads Mermaid from a CDN module (build_site gallery-only bootstrap) so the live demo renders SVG the same way Dazzle does when the host emitter appends the Mermaid loader. The library swaps the <pre class=mermaid> for SVG at runtime — source styling only matters for the initial paint flash. The wrapper owns overflow; dz-diagram-empty is the no-data paragraph.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/diagram.py`
