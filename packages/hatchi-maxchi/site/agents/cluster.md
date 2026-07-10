# Cluster (`cluster`)

A wrapping horizontal group — buttons, chips, metadata rows. Items keep their size and wrap when the line runs out.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="cluster" data-gap="sm"><button class="button" data-variant="primary">Save</button><button class="button" data-variant="outline">Cancel</button><span class="badge" data-tone="neutral">Draft</span></div>
```

## Guidance (prose; HTML from the registry notes field)

Flex row + <code>flex-wrap</code> + <code>gap</code>. <code>data-dz-gap</code> as on stack. <code>data-dz-align</code> (<code>center|start|end|baseline</code>, default center) sets cross-axis alignment; <code>data-dz-justify</code> (<code>start|end|between|center</code>, default start) distributes the line. Never fixes widths — that's what makes it safe for translation-length and zoom changes.
