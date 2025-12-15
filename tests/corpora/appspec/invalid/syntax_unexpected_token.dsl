# Invalid: Unexpected token - missing colon after entity name
# Expected error: ParseError at line 6
module corpus.invalid.syntax
app syntax_error "Syntax Error"

entity Task "Task"
  id: uuid pk
  title: str(200) required
