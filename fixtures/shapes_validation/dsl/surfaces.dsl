module shapes_validation.surfaces

use shapes_validation.entities

surface realm_list "Realms":
  uses entity Realm
  mode: list
  access: authenticated
  section main:
    field name "Name"
    field sigil "Sigil"

  ux:
    sort: name asc
    search: name
    filter: sigil
    empty: "No realms found."

surface shape_list "Shapes":
  uses entity Shape
  mode: list
  access: authenticated
  section main:
    field name "Name"
    field form "Form"
    field colour "Colour"
    field material "Material"

  ux:
    sort: name asc
    search: name
    filter: form, colour, material
    empty: "No shapes found."

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

surface shape_create "Create Shape":
  uses entity Shape
  mode: create
  section main:
    field name "Name"
    field form "Form"
    field colour "Colour"
    field material "Material"
    field realm "Realm"
  ux:
    purpose: "Create a new shape in a realm"

surface shape_edit "Edit Shape":
  uses entity Shape
  mode: edit
  section main:
    field name "Name"
    field form "Form"
    field colour "Colour"
    field material "Material"
  ux:
    purpose: "Modify shape properties"

surface inscription_list "Inscriptions":
  uses entity Inscription
  mode: list
  access: authenticated
  section main:
    field text "Text"
    field shape "Shape"
    field author "Author"

  ux:
    sort: created_at desc
    search: text
    filter: shape, author
    empty: "No inscriptions found."
