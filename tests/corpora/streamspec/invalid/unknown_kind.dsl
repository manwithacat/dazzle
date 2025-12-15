# Invalid: Unknown record kind
# Expected error: ParseError - Invalid record kind 'EVENT'
module corpus.stream.invalid.unknown_kind
app invalid_stream "Invalid Stream"

stream order_facts:
  kind: EVENT

  schema OrderPlaced:
    order_id: uuid required
    placed_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: placed_at
