# Empty state (`empty-state`)

Icon + one sentence + primary action — never a bare 'No X'.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="card card-body hm-measure">
  <div class="empty-state">
    <span class="empty-state__icon"><svg class="icon" aria-hidden="true"><use href="#i-inbox"/></svg></span>
    <h3 class="empty-state__title">No invoices yet</h3>
    <p class="empty-state__description">Create your first invoice to get started.</p>
    <div class="empty-state__action"><a class="button" data-variant="primary" href="#">New Invoice</a></div>
  </div>
</div>
```
