# Minimal valid INTENT stream
module corpus.stream.intent
app stream_intent "Minimal Intent Stream"

stream order_placement_requests:
  kind: INTENT
  description: "Requests to place orders"

  schema OrderPlacementRequested:
    request_id: uuid required
    order_id: uuid required
    customer_id: uuid required
    requested_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: requested_at

  outcomes:
    success:
      emits OrderPlaced from order_facts
    failure:
      emits OrderPlacementRejected from order_facts
