# Invalid: Missing required 'partition_key' field
# Expected error: ParseError - Stream must specify partition_key
module corpus.stream.invalid.missing_partition
app invalid_stream "Invalid Stream"

stream order_facts:
  kind: FACT

  schema OrderPlaced:
    order_id: uuid required
    placed_at: datetime required

  ordering_scope: per_order
  t_event: placed_at
