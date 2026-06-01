module transition_atomic.core
app transition_atomic "Transition→Atomic Seam Fixture"

# ADR-0032 Slice A (#1319) — an `on_transition: invoke <flow>(...)` declares + binds
# a guarded atomic flow as a transition effect. SURFACE ONLY: the binding parses
# and validates (flow exists, required inputs bound, `self` = the transitioning
# row). The shared-transaction runtime wiring (status write + flow commit together)
# is ADR-0032 Slice B.

entity Order "Order":
  id: uuid pk
  status: enum[submitted,fulfilled]=submitted
  warehouse: str(40)

  permit:
    create: role(admin)
    read: role(admin)
    list: role(admin)
    update: role(admin)

  transitions:
    submitted -> fulfilled: role(admin)

  on_transition:
    submitted -> fulfilled:
      invoke fulfil_order(order: self, warehouse: input.warehouse)

entity Shipment "Shipment":
  id: uuid pk
  order: ref Order required
  warehouse: str(40) required

  permit:
    create: role(admin)
    read: role(admin)
    list: role(admin)

atomic fulfil_order "Fulfil Order":
  intent: "Create the shipment for a fulfilled order, in one transaction"
  permit:
    execute: role(admin)
  input order: ref Order required
  input warehouse: str(40) required
  create Shipment:
    order: input.order
    warehouse: input.warehouse
