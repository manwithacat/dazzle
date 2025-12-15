# Minimal valid FACT stream
module corpus.stream.fact
app stream_fact "Minimal Fact Stream"

stream order_facts:
  kind: FACT
  description: "Immutable facts about orders"

  schema OrderPlaced:
    order_id: uuid required
    total_amount: decimal(10,2) required
    placed_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: placed_at
