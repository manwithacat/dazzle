module test.core
app a "A"

foreign_model Thing from stripe "Thing":
  key: thing_id
  constraint not_a_real_kind
