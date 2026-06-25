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

  scope:
    list: all
      as: admin

entity User "User":
  display_field: name
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

  scope:
    list: all
      as: admin

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
    field notes "Notes (compact toolbar, capped)" widget=rich_text rich_text_toolbar="bold,italic,link" rich_text_max_length="5000"
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
  access: persona(admin)
  all_items:
    source: Showcase
    display: grid
    sort: created_at desc

  by_status:
    source: Showcase
    display: kanban
    group_by: status

# ── UX Catalogue — one region per display mode (the docs catalogue source) ──

entity Box "Box":
  display_field: name
  id: uuid pk
  name: str(80) required
  team: enum[platform,payments,growth,data]=platform
  status: enum[healthy,degraded,critical]=healthy
  latency_ms: int
  error_rate: decimal(5,2)
  target_ms: int
  opened_at: datetime

  permit:
    list: role(admin)
    read: role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      as: admin

surface box_list "Boxes":
  uses entity Box
  mode: list
  section main:
    field name "Name"
    field team "Team"
    field status "Status"
    field latency_ms "Latency (ms)"
    field error_rate "Error Rate"

workspace ux_catalogue "UX Catalogue":
  access: persona(admin)
  cat_list:
    source: Box
    display: list
    sort: name asc
    outlier_on: latency_ms
    outlier_method: iqr
    empty: "No boxes"

  cat_metrics:
    source: Box
    display: metrics
    aggregate:
      total: count(Box)
      critical: count(Box where status = critical)
      avg_latency: avg(latency_ms)

  cat_bar_chart:
    source: Box
    display: bar_chart
    group_by: team
    aggregate:
      count: count(Box)
    empty: "No boxes"

  cat_comparison:
    source: Box
    display: comparison
    group_by: team
    aggregate:
      total: count(Box)
    rank_by: total
    order: desc
    outlier_method: iqr
    empty: "No boxes"

  cat_heatmap:
    source: Box
    display: heatmap
    rows: team
    columns: status
    value: latency_ms
    empty: "No boxes"

  cat_pivot:
    source: Box
    display: pivot_table
    group_by: [team, status]
    aggregate:
      count: count(Box)
    empty: "No boxes"

  cat_bullet:
    source: Box
    display: bullet
    bullet_label: name
    bullet_actual: latency_ms
    bullet_target: target_ms
    empty: "No boxes"

  cat_kanban:
    source: Box
    display: kanban
    group_by: status
    empty: "No boxes"

  cat_insight:
    source: Box
    display: insight_summary
    group_by: team
    aggregate:
      count: count(Box)

  cat_rag:
    source: Box
    display: list
    rag_on: error_rate
    tone_bands:
      - at: 5
        tone: destructive
      - at: 1
        tone: warning
      - at: 0
        tone: positive
