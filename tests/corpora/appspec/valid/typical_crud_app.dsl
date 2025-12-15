# Typical CRUD application pattern
module corpus.typical_crud
app typical_crud "Typical CRUD App"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required
  email: email optional
  phone: str(50) optional
  status: enum[active,inactive]=active
  created_at: datetime required

surface contact_list "Contact List":
  uses entity Contact
  mode: list
  section main:
    field name "Name"
    field email "Email"
    field status "Status"

surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view
  section main:
    field name "Name"
    field email "Email"
    field phone "Phone"
    field status "Status"
    field created_at "Created"

surface contact_create "Create Contact":
  uses entity Contact
  mode: create
  section main:
    field name "Name"
    field email "Email"
    field phone "Phone"
  action save "Save":
    on submit -> surface contact_list

surface contact_edit "Edit Contact":
  uses entity Contact
  mode: edit
  section main:
    field name "Name"
    field email "Email"
    field phone "Phone"
    field status "Status"
  action save "Save":
    on submit -> surface contact_list
