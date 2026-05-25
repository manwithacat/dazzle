---
id: god_entities
name: God entities
layer: inference
status: active
summary: >-
  Single-entity-spans-everything modelling — Order with 20 fields covering
  address, payment, delivery, line items, status, history. The corpus reflex
  is "put everything in one model"; the right shape is decomposition through
  refs, where each entity owns a coherent concern with its own lifecycle and
  RBAC surface.
triggers_text:
  - "too many fields"
  - "large entity"
  - "god entity"
  - "monolith entity"
  - "kitchen sink"
  - "single big model"
  - "all the fields on one entity"
triggers_code:
  - '^entity\s+\w+\s+"[^"]+":\s*\n(?:\s+\w+\s*:\s*\S+\s*\n){15,}'
refs:
  adrs: []
  kb_patterns:
    - no_god_entities
  tests: []
---

# God entities

## The corpus prior

Rails / Django / ActiveRecord tutorials are full of models that accrete fields. `Order` starts with `customer_id` and `total`, and three releases later it has shipping address fields, payment-method fields, line-item counters, delivery-status timestamps, customer notes, and an admin-override flag. Stack Overflow accepts this as normal — top answers to "how do I model an order" routinely show 15+ fields on one model.

LLMs follow the corpus. Given a spec describing orders, an agent emits one giant entity because that's what every "Rails order model" example in training did.

## Wrong shape

```dsl
entity Order "Order":
  id: uuid pk
  customer_email: str(200) required
  customer_phone: str(20)
  shipping_street: str(200)
  shipping_city: str(100)
  shipping_postcode: str(20)
  shipping_country: str(2)
  payment_method: enum[card, paypal, transfer]
  payment_last4: str(4)
  payment_status: enum[pending, paid, refunded]
  delivery_carrier: str(50)
  delivery_tracking: str(100)
  delivery_eta: date
  delivered_at: datetime
  total: decimal(10,2)
  line_count: int
  notes: text
  admin_override: bool=false
  status: enum[draft, placed, shipped, delivered, cancelled]
  ...
```

What this gives up: every surface that touches Order has to deal with all 20+ fields. RBAC is overly broad — "can read Order" gives access to payment internals, customer PII, admin overrides. State transitions get tangled because the entity has multiple lifecycles (payment, delivery, fulfilment) braided together. Scope rules become brittle because "customer can see their orders" now has to reason about which subset of fields the customer should see. Schema evolution touches everyone.

## Right shape

Each entity owns one coherent concern. Use `ref` to compose:

```dsl
entity Order "Order":
  id: uuid pk
  customer: ref Customer required
  shipping_address: ref Address
  status: enum[draft, placed, shipped, delivered, cancelled]=draft
  placed_at: datetime
  total: decimal(10,2)

entity OrderLine "Order Line":
  id: uuid pk
  order: ref Order required
  product: ref Product required
  quantity: int required
  unit_price: decimal(10,2) required

entity Payment "Payment":
  id: uuid pk
  order: ref Order required
  method: enum[card, paypal, transfer]
  status: enum[pending, paid, refunded]
  amount: decimal(10,2)

entity Delivery "Delivery":
  id: uuid pk
  order: ref Order required
  carrier: str(50)
  tracking: str(100)
  eta: date
  delivered_at: datetime
```

Each piece now has its own surfaces, its own RBAC permits, its own scope rules, its own state machine. The Order surface for a customer can show "your order is shipped" without leaking payment internals. The admin payment-reconciliation surface can scope on Payment without dragging the whole Order entity through.

## Why this matters here

Dazzle's DSL is built around the assumption that entities are *coherent units of authority and lifecycle* — RBAC permits attach to entities, scope rules traverse refs, state machines belong to entities. A god entity collapses all those axes onto one row and makes every downstream construct harder to reason about. The framework's value emerges when the entity boundaries match the conceptual boundaries; god entities erase that match.

A useful heuristic: if you can't write a coherent sentence about what one entity *is* without using the word "and" twice, decompose.

## Cross-references

- Inference KB `no_god_entities` — bootstrap auto-surfacing via `spec_analyze.propose_patterns`.
- `docs/reference/project-layout.md` — entity decomposition examples.
