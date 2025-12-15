# Invalid: Missing required 't_event' field
# Expected error: ParseError - Stream must specify t_event
module corpus.stream.invalid.missing_t_event
app invalid_stream "Invalid Stream"

stream order_facts:
  kind: FACT

  schema OrderPlaced:
    order_id: uuid required
    placed_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
