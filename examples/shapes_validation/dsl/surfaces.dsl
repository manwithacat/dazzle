module shapes_validation.surfaces

use shapes_validation.entities

surface realm_list "Realms":
  uses entity Realm
  mode: list
  access: authenticated
  section main:
    field name "Name"
    field sigil "Sigil"

surface shape_list "Shapes":
  uses entity Shape
  mode: list
  access: authenticated
  section main:
    field name "Name"
    field form "Form"
    field colour "Colour"
    field material "Material"

surface shape_detail "Shape Detail":
  uses entity Shape
  mode: view
  access: authenticated
  section main:
    field name
    field form
    field colour
    field material
    field realm
    field creator

surface inscription_list "Inscriptions":
  uses entity Inscription
  mode: list
  access: authenticated
  section main:
    field text "Text"
    field shape "Shape"
    field author "Author"
