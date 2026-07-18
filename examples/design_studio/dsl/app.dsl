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
  default_workspace: studio_dashboard

persona designer "Designer":
  role: designer
  description: "Creates and manages design assets"
  default_workspace: studio_dashboard

persona reviewer "Reviewer":
  role: reviewer
  description: "Reviews and approves assets"
  # Answer-first: review queue desk (product maturity)
  default_workspace: review_desk

# ── Entities ─────────────────────────────────────────────────────────

entity User "User":
  display_field: name
  id: uuid pk
  email: str(200) unique required pii(category=contact)
  name: str(100) required pii(category=identity)
  role: enum[admin,designer,reviewer]=designer
  created_at: datetime auto_add

  permit:
    list: role(admin) or role(designer) or role(reviewer)
    read: role(admin) or role(designer) or role(reviewer)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    # list-only was insufficient: detail routes use gated_read → scope:read
    # (#1123). Missing read → default-deny 404 even when list rows exist.
    list: all
      as: admin, designer, reviewer
    read: all
      as: admin, designer, reviewer
    create: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin

entity Brand "Brand":
  display_field: name
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

  scope:
    list: all
      as: admin, designer, reviewer
    read: all
      as: admin, designer, reviewer
    create: all
      as: admin, designer
    update: all
      as: admin, designer
    delete: all
      as: admin

entity Asset "Design Asset":
  display_field: name
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
    # Reviewer updates status on the review-queue edit surface (and
    # transition buttons); designer owns create/content edits.
    update: role(admin) or role(designer) or role(reviewer)
    delete: role(admin)

  scope:
    list: all
      as: admin, designer, reviewer
    read: all
      as: admin, designer, reviewer
    create: all
      as: admin, designer
    update: all
      as: admin, designer, reviewer
    delete: all
      as: admin

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

  scope:
    list: all
      as: admin, designer, reviewer
    read: all
      as: admin, designer, reviewer
    create: all
      as: admin, designer
    update: all
      as: admin, designer
    delete: all
      as: admin

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

  scope:
    list: all
      as: admin, designer, reviewer
    read: all
      as: admin, designer, reviewer
    create: all
      as: admin, reviewer
    update: all
      as: admin
    delete: all
      as: admin

# ── Workspaces ───────────────────────────────────────────────────────

# Story-driven: designer home = metrics + recent work; reviewer home =
# review_desk / asset_catalog (docs/guides/story-to-composition.md).
workspace studio_dashboard "Studio Dashboard":
  access: persona(admin, designer, reviewer)
  portfolio:
    source: Asset
    display: metrics
    aggregate:
      assets: count(Asset)
      in_review: count(Asset where status = review)
      brands: count(Brand)
      campaigns: count(Campaign)
    tones:
      in_review: warning
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

# #1626 P0-7: not a visual media gallery (no thumbnails/swatches yet) — honest catalog.
workspace asset_catalog "Asset Catalog":
  purpose: "Browse assets as a card grid and metrics (not a thumbnail media gallery yet)"
  access: persona(admin, designer, reviewer)
  catalog_metrics:
    source: Asset
    display: metrics
    aggregate:
      draft: count(Asset where status = draft)
      in_review: count(Asset where status = review)
      approved: count(Asset where status = approved)
    tones:
      in_review: warning
      approved: positive
  asset_grid:
    source: Asset
    display: grid
    sort: created_at desc
  review_queue:
    source: Asset
    filter: status = review
    sort: updated_at asc
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"

# Product maturity: extra job desks lower warehouse density (7 lists / 2 ws).
workspace brand_desk "Brand Desk":
  purpose: "Brand portfolio — identity first, then assets and campaigns"
  access: persona(admin, designer)
  brand_metrics:
    source: Brand
    display: metrics
    aggregate:
      brands: count(Brand)
      assets: count(Asset)
      campaigns: count(Campaign)
    tones:
      brands: accent
  brand_grid:
    source: Brand
    display: grid
    sort: name asc
  campaign_queue:
    source: Campaign
    filter: status = active
    sort: name asc
    display: queue
    empty: "No active campaigns"

workspace review_desk "Review Desk":
  purpose: "Reviewer job — clear the in-review queue before browsing the catalog"
  access: persona(admin, designer, reviewer)
  review_load:
    source: Asset
    display: metrics
    aggregate:
      in_review: count(Asset where status = review)
      draft: count(Asset where status = draft)
      approved: count(Asset where status = approved)
    tones:
      in_review: warning
      approved: positive
  awaiting_review:
    source: Asset
    filter: status = review
    sort: updated_at asc
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"
  recently_approved:
    source: Asset
    filter: status = approved
    sort: updated_at desc
    limit: 12
    display: queue
    empty: "No recent approvals"

# ── Surfaces ─────────────────────────────────────────────────────────

surface brand_list "Brands":
  uses entity Brand
  mode: list
  open: Brand via id
  section main:
    field name "Name"
    # #1626 P0-8: color widgets render as swatches in list (not raw hex text)
    field primary_color "Primary" widget=color
    field secondary_color "Secondary" widget=color
    field accent_color "Accent" widget=color
    field created_by "Creator"
  ux:
    purpose: "Browse brands with palette swatches — open a row for the brand hub"

surface brand_create "New Brand":
  uses entity Brand
  mode: create
  section identity:
    field name "Brand Name"
    field description "Description" widget=rich_text
  section colors:
    field primary_color "Primary Color" widget=color
    field secondary_color "Secondary Color" widget=color
    field accent_color "Accent Color" widget=color

surface brand_detail "Brand Detail":
  uses entity Brand
  mode: view
  section identity "Identity":
    field name "Name"
    field description "Description"
    field created_by "Creator"
  section palette "Palette":
    layout: strip
    field primary_color "Primary" widget=color
    field secondary_color "Secondary" widget=color
    field accent_color "Accent" widget=color


  related assets "Assets":
    display: status_cards
    show: Asset

  related campaigns "Campaigns":
    display: table
    show: Campaign

  ux:
    purpose: "Brand hub — identity, palette strip, assets and campaigns"

surface asset_list "Assets":
  uses entity Asset
  mode: list
  open: Brand via brand
  section main:
    field name "Name"
    field asset_type "Type"
    field status "Status"
    field brand "Brand"
    field tags "Tags"
    field quality_score "Quality"
  ux:
    purpose: "Browse assets — open a row for the parent Brand hub"

surface asset_create "New Asset":
  uses entity Asset
  mode: create
  section details:
    field name "Asset Name"
    field description "Description" widget=rich_text
    field brand "Brand" widget=combobox
    field asset_type "Type"
  section metadata:
    field tags "Tags" widget=tags
    field quality_score "Quality Score" widget=slider
    field file "File"

surface asset_detail "Asset Detail":
  uses entity Asset
  mode: view
  section summary "Summary":
    field name "Name"
    field description "Description"
    field brand "Brand"
  section production "Production":
    layout: strip
    field asset_type "Type"
    field status "Status"
    field quality_score "Quality"
    field tags "Tags"

  related feedback "Feedback":
    display: table
    show: Feedback

  ux:
    purpose: "Asset hub — production strip and related feedback"

surface asset_edit "Edit Asset":
  uses entity Asset
  mode: edit
  section details:
    field name "Name"
    field description "Description" widget=rich_text
    field tags "Tags" widget=tags
    field quality_score "Quality" widget=slider
    field status "Status"

surface campaign_create "New Campaign":
  uses entity Campaign
  mode: create
  section details:
    field name "Campaign Name"
    field description "Brief" widget=rich_text
    field brand "Brand" widget=combobox
  section schedule:
    field start_date "Start Date" widget=picker
    field end_date "End Date" widget=picker
    field budget "Budget"

surface campaign_detail "Campaign Detail":
  uses entity Campaign
  mode: view
  section summary "Summary":
    field name "Name"
    field description "Brief"
    field brand "Brand"
  section schedule "Schedule":
    layout: strip
    field status "Status"
    field start_date "Start"
    field end_date "End"
    field budget "Budget"
  ux:
    purpose: "Campaign hub — brand context and schedule strip"

surface feedback_create "Add Feedback":
  uses entity Feedback
  mode: create
  section main:
    field rating "Rating" widget=slider
    field comment "Comment" widget=rich_text

surface feedback_list "Feedback":
  uses entity Feedback
  mode: list
  open: Asset via asset
  section main:
    field asset "Asset"
    field reviewer "Reviewer"
    field rating "Rating"
    field comment "Comment"
    field created_at "Date"
  ux:
    purpose: "Feedback trail — open a row for the parent Asset hub"
    sort: created_at desc
    filter: asset, reviewer
    empty: "No feedback submitted yet."

# View surface so ST-004 story_coverage sees Feedback.view for reviewer
# (related table alone was not enough for discovery coherence).
# open: is list-only (#1603) — hop to parent is via asset field + list open.
surface feedback_detail "Feedback Detail":
  uses entity Feedback
  mode: view
  section summary "Feedback":
    field asset "Asset"
    field reviewer "Reviewer"
    field rating "Rating"
    field comment "Comment"
    field created_at "Date"
  ux:
    purpose: "Read a feedback note in context of the parent Asset"

surface feedback_edit "Edit Feedback":
  uses entity Feedback
  mode: edit
  access: persona(admin)
  section main:
    field rating "Rating" widget=slider
    field comment "Comment" widget=rich_text

surface brand_edit "Edit Brand":
  uses entity Brand
  mode: edit
  section identity:
    field name "Brand Name"
    field description "Description" widget=rich_text
  section colors:
    field primary_color "Primary Color" widget=color
    field secondary_color "Secondary Color" widget=color
    field accent_color "Accent Color" widget=color

surface campaign_list "Campaigns":
  uses entity Campaign
  mode: list
  open: Brand via brand
  section main:
    field name "Name"
    field brand "Brand"
    field status "Status"
    field start_date "Start"
    field end_date "End"
  ux:
    purpose: "Browse campaigns — open a row for the parent Brand hub"

surface campaign_edit "Edit Campaign":
  uses entity Campaign
  mode: edit
  section details:
    field name "Campaign Name"
    field description "Brief" widget=rich_text
    field brand "Brand" widget=combobox
  section schedule:
    field start_date "Start Date" widget=picker
    field end_date "End Date" widget=picker
    field budget "Budget"
