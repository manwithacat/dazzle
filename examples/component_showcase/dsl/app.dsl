# Component Showcase — Visual gallery of all Dazzle UX components
# Every widget type exercised on a single entity for quick visual regression testing

module component_showcase.core

app component_showcase "Component Showcase":
  security_profile: basic

persona admin "Admin":
  role: admin
  description: "Full access"

# ── Kitchen Sink Entity ──────────────────────────────────────────────

entity Showcase "Component Showcase":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[draft,active,archived]=draft
  category: enum[alpha,beta,gamma,delta]=alpha
  is_featured: bool=false
  priority: int
  rating: int
  color_hex: str(7)
  tags: str(500)
  assigned_to: ref User
  start_date: date
  end_date: date
  due_datetime: datetime
  budget: decimal(10,2)
  notes: text
  attachment: file
  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    draft -> active
    active -> archived
    archived -> draft: role(admin)

  permit:
    list: role(admin)
    read: role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  role: enum[admin]=admin
  created_at: datetime auto_add

  permit:
    list: role(admin)
    read: role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

# ── Surfaces ─────────────────────────────────────────────────────────

surface showcase_list "All Components":
  uses entity Showcase
  mode: list
  section main:
    field title "Title"
    field status "Status"
    field category "Category"
    field is_featured "Featured"
    field tags "Tags"
    field color_hex "Color"
    field start_date "Start"

surface showcase_create "Create Showcase":
  uses entity Showcase
  mode: create
  section text_inputs:
    field title "Plain Text Input"
    field description "Rich Text (textarea)" widget=rich_text
    field notes "Notes (textarea)" widget=rich_text
  section selection_inputs:
    field status "Status (select)"
    field category "Category (select)"
    field assigned_to "Assigned To (ref)" widget=combobox
    field is_featured "Featured (checkbox)"
  section date_inputs:
    field start_date "Start Date (date)" widget=picker
    field end_date "End Date (date)" widget=picker
    field due_datetime "Due (datetime)" widget=picker
  section numeric_inputs:
    field priority "Priority (number)" widget=slider
    field rating "Rating (number)" widget=slider
    field budget "Budget (decimal)"
  section other_inputs:
    field color_hex "Color Hex (text)" widget=color
    field tags "Tags (text)" widget=tags
    field attachment "Attachment (file)"

surface showcase_detail "Showcase Detail":
  uses entity Showcase
  mode: view
  section main:
    field title "Title"
    field description "Description"
    field status "Status"
    field category "Category"
    field is_featured "Featured"
    field assigned_to "Assigned To"
    field tags "Tags"
    field color_hex "Color"
    field start_date "Start"
    field end_date "End"
    field due_datetime "Due"
    field priority "Priority"
    field rating "Rating"
    field budget "Budget"
    field notes "Notes"
    field attachment "Attachment"

surface showcase_edit "Edit Showcase":
  uses entity Showcase
  mode: edit
  section text_inputs:
    field title "Title"
    field description "Description" widget=rich_text
    field notes "Notes" widget=rich_text
  section selection_inputs:
    field status "Status"
    field category "Category"
    field assigned_to "Assigned To" widget=combobox
    field is_featured "Featured"
  section dates:
    field start_date "Start Date" widget=picker
    field end_date "End Date" widget=picker
    field due_datetime "Due" widget=picker
  section numeric:
    field priority "Priority" widget=slider
    field rating "Rating" widget=slider
    field budget "Budget"
  section other:
    field color_hex "Color" widget=color
    field tags "Tags" widget=tags

# ── Workspace ────────────────────────────────────────────────────────

workspace gallery "Component Gallery":
  all_items:
    source: Showcase
    display: grid
    sort: created_at desc

  by_status:
    source: Showcase
    display: kanban
    group_by: status
