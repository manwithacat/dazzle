# Invalid: Entity with invalid field type
# Expected error: ParseError - unknown type
module corpus.invalid.badtype
app badtype "Bad Type"

entity Task "Task":
  id: uuid pk
  name: invalidtype(100)
