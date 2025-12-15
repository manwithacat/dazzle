# Invalid: Malformed entity - missing title and fields
# Expected error: ParseError - unexpected token
module corpus.invalid.malformed
app malformed "Malformed"

entity Task
  id uuid pk
