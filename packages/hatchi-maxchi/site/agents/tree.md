# Tree (`tree`)

Hierarchy on native <details>/<summary> — indented children, rotating chevron, child-count chips. No JS at all.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="hm-measure">
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
```

## Guidance (prose; HTML from the registry notes field)

Pure hypermedia: state is the native <code>open</code> attribute, the chevron rotation keys off <code>.dz-tree-node[open]</code>, and each level indents via its <code>dz-tree-children</code> wrapper. The server emits depth-0 nodes <code>open</code> by default; the count chip renders only for nodes with children.
