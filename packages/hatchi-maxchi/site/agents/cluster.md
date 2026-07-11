# Cluster (`cluster`)

A wrapping horizontal group — buttons, chips, metadata rows. Items keep their size and wrap when the line runs out.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="cluster" data-gap="sm"><button class="button" data-variant="primary">Save</button><button class="button" data-variant="outline">Cancel</button><span class="badge" data-tone="neutral">Draft</span></div>
```

## Notes

Flex row + flex-wrap + gap. data-dz-gap as on stack. data-dz-align (center|start|end|baseline, default center) sets cross-axis alignment; data-dz-justify (start|end|between|center, default start) distributes the line. Never fixes widths — that's what makes it safe for translation-length and zoom changes.
