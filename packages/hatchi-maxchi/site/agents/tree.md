# Tree (`tree`)

Hierarchy on native <details>/<summary> — indented children, rotating chevron, child-count chips. No JS at all.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

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

Pure hypermedia: state is the native open attribute, the chevron rotation keys off .dz-tree-node[open], and each level indents via its dz-tree-children wrapper. The server emits depth-0 nodes open by default; the count chip renders only for nodes with children.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
