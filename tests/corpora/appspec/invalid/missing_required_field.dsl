# Invalid: Entity without colon
# Expected error: ParseError - expected colon
module corpus.invalid.missing_colon
app missing_colon "Missing Colon"

entity Task "Task"
  id: uuid pk
