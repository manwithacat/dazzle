# Stem: SSR + client slot parity

## Claim

When a Hyperpart unit can be emitted from **server HTML** (OOB / fragment) **or**
from a **client event detail**, both paths must build the **same dual-lock slots**
from one shared slot model. Divergence is a product bug class (toasts that look
different by origin, missing actions on one path, etc.).

## Reconstruct

1. **Define slots** in the contract / agent pack (title, message, actions, actor…).
2. **One server builder** produces the unit HTML (e.g. `toast_unit_html(slots)`).
3. **One client builder** maps `CustomEvent.detail` → the same DOM shape.
4. **Host** may ensure optional host-owned chrome (progress bar, default icon)
   but must not invent a second notification model.
5. Prefer **optional** dual-lock nodes for new slots so existing emitters stay valid.

### Detail object convention (client)

```js
{
  message: string,          // required for toast
  type?: "info"|"success"|"warning"|"error",
  title?: string,
  actions?: [{ label, href? }],
  actor?: { name, avatar? },  // person composition
  duration?: "8s",
  sound?: boolean,            // unit wants cue; page must still opt in
}
```

Server kwargs mirror the same names.

## Not this

- Alpine `x-for` stacks as the source of truth.
- Client-only markup that the server path cannot reproduce.
- Requiring contracts for every host-injected affordance (progress, default icon).

## Expressions

- Toast: `response_helpers.toast_unit_html` / `with_toast` + `dz-toast.js` clientToast
- Decision 0011 phases D–F
