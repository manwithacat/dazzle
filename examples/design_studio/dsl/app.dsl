# Design Studio — Brand & Design Asset Management
# Exercises: color picker, multi-select, toggle group, context menu,
# rating, slider, rich text, date picker, steps indicator, stat cards

module design_studio.core

app design_studio "Design Studio":
  security_profile: basic

feedback_widget: enabled

# ── Personas ─────────────────────────────────────────────────────────

persona admin "Admin":
  role: admin
  description: "Full access to all brands and assets"

persona designer "Designer":
  role: designer
  description: "Creates and manages design assets"

persona reviewer "Reviewer":
  role: reviewer
  description: "Reviews and approves assets"

# ── Entities ─────────────────────────────────────────────────────────

entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  role: enum[admin,designer,reviewer]=designer
  created_at: datetime auto_add

  permit:
    list: role(admin) or role(designer) or role(reviewer)
    read: role(admin) or role(designer) or role(reviewer)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

entity Brand "Brand":
  id: uuid pk
  name: str(200) required
  description: text
  primary_color: str(7)
  secondary_color: str(7)
  accent_color: str(7)
  logo_url: str(500)
  created_by: ref User
  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    list: role(admin) or role(designer) or role(reviewer)
    read: role(admin) or role(designer) or role(reviewer)
    create: role(admin) or role(designer)
    update: role(admin) or role(designer)
    delete: role(admin)

entity Asset "Design Asset":
  id: uuid pk
  brand: ref Brand required
  name: str(200) required
  description: text
  asset_type: enum[logo,icon_glyph,illustration,photo,pattern,typography]=logo
  status: enum[draft,review,approved,published,archived]=draft
  file: file
  tags: str(500)
  quality_score: int
  created_by: ref User
  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    draft -> review
    review -> approved: role(admin) or role(reviewer)
    review -> draft
    approved -> published: role(admin)
    published -> archived: role(admin)
    archived -> draft: role(admin)

  permit:
    list: role(admin) or role(designer) or role(reviewer)
    read: role(admin) or role(designer) or role(reviewer)
    create: role(admin) or role(designer)
    update: role(admin) or role(designer)
    delete: role(admin)

entity Campaign "Campaign":
  id: uuid pk
  name: str(200) required
  description: text
  brand: ref Brand required
  status: enum[planning,active,completed,cancelled]=planning
  start_date: date
  end_date: date
  budget: decimal(10,2)
  created_by: ref User
  created_at: datetime auto_add

  transitions:
    planning -> active
    active -> completed
    active -> cancelled
    completed -> planning: role(admin)

  permit:
    list: role(admin) or role(designer) or role(reviewer)
    read: role(admin) or role(designer) or role(reviewer)
    create: role(admin) or role(designer)
    update: role(admin) or role(designer)
    delete: role(admin)

entity Feedback "Design Feedback":
  id: uuid pk
  asset: ref Asset required
  reviewer: ref User required
  rating: int
  comment: text
  created_at: datetime auto_add

  permit:
    list: role(admin) or role(designer) or role(reviewer)
    read: role(admin) or role(designer) or role(reviewer)
    create: role(admin) or role(reviewer)
    update: role(admin)
    delete: role(admin)

# ── Workspaces ───────────────────────────────────────────────────────

workspace studio_dashboard "Studio Dashboard":
  brands:
    source: Brand
    display: grid
    sort: name asc
  recent_assets:
    source: Asset
    display: grid
    sort: updated_at desc
  campaigns:
    source: Campaign
    display: metrics

workspace asset_gallery "Asset Gallery":
  gallery:
    source: Asset
    display: grid
    sort: created_at desc
  review_queue:
    source: Asset
    display: queue

# ── Surfaces ─────────────────────────────────────────────────────────

surface brand_list "Brands":
  uses entity Brand
  mode: list
  section main:
    field name "Name"
    field primary_color "Primary"
    field secondary_color "Secondary"
    field created_by "Creator"

surface brand_create "New Brand":
  uses entity Brand
  mode: create
  section identity:
    field name "Brand Name"
    field description "Description"
  section colors:
    field primary_color "Primary Color"
    field secondary_color "Secondary Color"
    field accent_color "Accent Color"

surface brand_detail "Brand Detail":
  uses entity Brand
  mode: view
  section main:
    field name "Name"
    field description "Description"
    field primary_color "Primary"
    field secondary_color "Secondary"
    field accent_color "Accent"

  related assets "Assets":
    display: status_cards
    show: Asset

  related campaigns "Campaigns":
    display: table
    show: Campaign

surface asset_list "Assets":
  uses entity Asset
  mode: list
  section main:
    field name "Name"
    field asset_type "Type"
    field status "Status"
    field brand "Brand"
    field tags "Tags"
    field quality_score "Quality"

surface asset_create "New Asset":
  uses entity Asset
  mode: create
  section details:
    field name "Asset Name"
    field description "Description"
    field brand "Brand"
    field asset_type "Type"
  section metadata:
    field tags "Tags"
    field quality_score "Quality Score"
    field file "File"

surface asset_detail "Asset Detail":
  uses entity Asset
  mode: view
  section main:
    field name "Name"
    field description "Description"
    field asset_type "Type"
    field status "Status"
    field brand "Brand"
    field tags "Tags"
    field quality_score "Quality"

  related feedback "Feedback":
    display: table
    show: Feedback

surface asset_edit "Edit Asset":
  uses entity Asset
  mode: edit
  section details:
    field name "Name"
    field description "Description"
    field tags "Tags"
    field quality_score "Quality"

surface campaign_create "New Campaign":
  uses entity Campaign
  mode: create
  section details:
    field name "Campaign Name"
    field description "Brief"
    field brand "Brand"
  section schedule:
    field start_date "Start Date"
    field end_date "End Date"
    field budget "Budget"

surface campaign_detail "Campaign Detail":
  uses entity Campaign
  mode: view
  section main:
    field name "Name"
    field description "Brief"
    field brand "Brand"
    field status "Status"
    field start_date "Start"
    field end_date "End"
    field budget "Budget"

surface feedback_create "Add Feedback":
  uses entity Feedback
  mode: create
  section main:
    field rating "Rating"
    field comment "Comment"
