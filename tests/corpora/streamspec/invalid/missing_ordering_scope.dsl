# Invalid: Missing required 'ordering_scope' field
# Expected error: ParseError - Stream must specify ordering_scope
module corpus.stream.invalid.missing_ordering
app invalid_stream "Invalid Stream"

stream order_facts:
  kind: FACT

  schema OrderPlaced:
    order_id: uuid required
    placed_at: datetime required

  partition_key: order_id
  t_event: placed_at
