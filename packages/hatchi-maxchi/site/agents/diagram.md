# Diagram (`diagram`)

A horizontal-scroll wrapper for server-emitted Mermaid source — the library replaces the <pre> with rendered SVG.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="diagram-scroll">
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
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

The gallery shows the raw source (Mermaid is not loaded here); in Dazzle the emitter appends the Mermaid loader script and the library swaps the <pre> for SVG at runtime — the source styling only matters for the initial paint flash. The wrapper owns overflow; dz-diagram-empty is the no-data paragraph.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
