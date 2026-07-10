# Separator (`separator`)

A hairline divider on the border token — horizontal (`<hr>`) or vertical (`role=separator`).

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="hm-stack hm-measure">
  <p class="hm-demo-muted">Account details</p>
  <hr class="separator">
  <p class="hm-demo-muted">Billing and invoices</p>
  <div class="hm-demo-row">
    <span class="hm-demo-muted">Draft</span>
    <div class="separator--vertical" role="separator" aria-orientation="vertical"></div>
    <span class="hm-demo-muted">Published</span>
    <div class="separator--vertical" role="separator" aria-orientation="vertical"></div>
    <span class="hm-demo-muted">Archived</span>
  </div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The horizontal rule is a native <code>&lt;hr&gt;</code> (implicitly <code>role=separator</code>); the vertical divider is a zero-width element with an explicit <code>role=separator</code> + <code>aria-orientation=&quot;vertical&quot;</code>.
