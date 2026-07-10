# Diagram (`diagram`)

A horizontal-scroll wrapper for server-emitted Mermaid source — the library replaces the <pre> with rendered SVG.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="diagram-scroll">
  <pre class="mermaid diagram-source">erDiagram
  CUSTOMER ||--o{ ORDER : places
  ORDER ||--|{ LINE_ITEM : contains</pre>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The gallery shows the raw source (Mermaid is not loaded here); in Dazzle the emitter appends the Mermaid loader script and the library swaps the <code>&lt;pre&gt;</code> for SVG at runtime — the source styling only matters for the initial paint flash. The wrapper owns overflow; <code>dz-diagram-empty</code> is the no-data paragraph.
