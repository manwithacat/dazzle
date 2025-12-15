# Minimal valid entity - smallest meaningful AppSpec
module corpus.minimal_entity
app minimal_entity "Minimal Entity"

entity Item "Item":
  id: uuid pk
  name: str(100) required
