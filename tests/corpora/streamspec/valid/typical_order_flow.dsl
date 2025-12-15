# Typical order processing streams
module corpus.stream.order_flow
app order_flow "Order Flow Streams"

stream order_placement_requests:
  kind: INTENT
  description: "Captures requests to place orders"

  schema OrderPlacementRequested:
    request_id: uuid required
    order_id: uuid required
    customer_id: uuid required
    amount_minor: int required
    currency: str(3) required
    requested_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: requested_at

  idempotency:
    type: deterministic_id
    field: request_id
    derivation: "hash(stream, order_id, customer_id, requested_at)"

  outcomes:
    success:
      emits OrderPlaced from order_facts
    failure:
      emits OrderPlacementRejected from order_facts
    timeout:
      emits OrderPlacementTimedOut from order_facts

stream order_facts:
  kind: FACT
  description: "Immutable facts about orders"

  schema OrderPlaced:
    order_id: uuid required
    customer_id: uuid required
    amount_minor: int required
    currency: str(3) required
    placed_at: datetime required
    causation_id: uuid required

  schema OrderPlacementRejected:
    order_id: uuid required
    customer_id: uuid required
    reason: str(500) required
    rejected_at: datetime required
    causation_id: uuid required

  schema OrderPlacementTimedOut:
    order_id: uuid required
    timed_out_at: datetime required
    causation_id: uuid required

  partition_key: order_id
  ordering_scope: per_order
  t_event: placed_at

  invariant: "OrderPlaced represents a completed and irreversible action"
  invariant: "No imperative language is permitted in FACT streams"

  side_effects:
    allowed: false
