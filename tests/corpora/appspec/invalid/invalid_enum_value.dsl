# Invalid: Invalid enum syntax - missing brackets
# Expected error: ParseError - unexpected token
module corpus.invalid.enum
app invalid_enum "Invalid Enum"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum low,medium,high
