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

## Notes

The gallery shows the raw source (Mermaid is not loaded here); in Dazzle the emitter appends the Mermaid loader script and the library swaps the <pre> for SVG at runtime — the source styling only matters for the initial paint flash. The wrapper owns overflow; dz-diagram-empty is the no-data paragraph.
