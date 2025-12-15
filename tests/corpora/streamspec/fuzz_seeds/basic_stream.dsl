# Fuzz seed: Minimal stream structure
module corpus.fuzz.stream
app fuzz_stream "Fuzz Stream"

stream s:
  kind: FACT

  schema S:
    id: uuid required
    x: str(10) required

  partition_key: id
  ordering_scope: per_id
  t_event: id
