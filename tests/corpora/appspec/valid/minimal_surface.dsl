# Minimal valid surface - entity + surface combo
module corpus.minimal_surface
app minimal_surface "Minimal Surface"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Task List":
  uses entity Task
  mode: list
  section main:
    field title "Title"
