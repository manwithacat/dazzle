# Edge case: Comments in various positions
# This is a file-level comment
module corpus.comments
app comments_test "Comments Test"

# Comment before entity
entity Task "Task":
  # Comment before field
  id: uuid pk
  # Another comment
  title: str(200) required
  # Comment with special chars
  status: enum[open,closed]=open

# Comment between constructs

surface task_list "Tasks":
  # Comment in surface
  uses entity Task
  mode: list
  # Section comment
  section main:
    # Field section comment
    field title "Title"
    field status "Status"

# Trailing comment
surface task_create "Create":
  uses entity Task
  mode: create
  section main:
    field title "Title"
  # Action comment
  action save "Save":
    on submit -> surface task_list
