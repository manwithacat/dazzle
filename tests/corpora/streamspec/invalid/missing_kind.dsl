# Invalid: Missing required 'kind' field
# Expected error: ParseError - Stream must specify kind
module corpus.stream.invalid.missing_kind
app invalid_stream "Invalid Stream"

stream order_facts:
  description: "Missing kind field"

  schema OrderPlaced:
    order_id: uuid required

  partition_key: order_id
  ordering_scope: per_order
  t_event: order_id
