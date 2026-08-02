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
  uses nav designer_nav

persona reviewer "Reviewer":
  role: reviewer
  description: "Reviews and approves assets"
  # Answer-first: review queue desk (product maturity)
  default_workspace: review_desk
  uses nav reviewer_nav

nav designer_nav:
  group "Studio":
    studio_dashboard
    brand_desk
    asset_catalog
    campaign_desk
    review_desk
    feedback_desk
    publish_desk
    draft_studio
    review_pipeline
    active_campaigns

nav reviewer_nav:
  group "Review":
    review_desk
    asset_catalog
    studio_dashboard
    feedback_desk
    publish_desk
    draft_studio
    review_pipeline
    active_campaigns

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
  # Goal B media: logo first in declaration so economy + queue meta prefer pixels.
  logo_url: url
  primary_color: str(7)
  secondary_color: str(7)
  accent_color: str(7)
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
  # Goal B media: HTTPS preview thumb on catalog cards (file binary stays optional).
  preview_url: url
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
  purpose: "Studio portfolio — metrics and mixed job views, not warehouse grids only"
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
  # Work-surface utility (cycle 1483 journey): brand portfolio is a pull-to-open
  # queue toward brand hubs — not a decorative card grid on the studio home.
  brands:
    source: Brand
    display: queue
    sort: name asc
    limit: 20
    action: brand_detail
    empty: "No brands yet"
  # Work-surface utility: recent updates are a dated stream (pair with asset_trail).
  recent_assets:
    source: Asset
    display: timeline
    sort: updated_at desc
    limit: 12
    action: asset_detail
    empty: "No assets yet"
  asset_trail:
    source: Asset
    sort: updated_at desc
    limit: 15
    display: timeline
    empty: "No assets yet"
  asset_status_mix:
    source: Asset
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Asset)
    empty: "No assets yet"
  review_pressure:
    source: Asset
    filter: status = review
    sort: updated_at asc
    limit: 12
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"

# Goal B media: catalog is a visual media shelf (preview thumbs + type labels),
# not a metadata-only warehouse. Brand palette strip anchors identity above fold.
workspace asset_catalog "Asset Catalog":
  purpose: "Media shelf — brand logos + palette, then asset preview thumbs (no metric delta theater)"
  access: persona(admin, designer, reviewer)
  # Brand identity strip first: logos + palette swatches (framework image/color).
  brand_palette:
    source: Brand
    display: queue
    sort: name asc
    limit: 8
    action: brand_detail
    empty: "No brands yet"
  # Visual media grid — preview_url thumbs + type · name titles.
  media_grid:
    source: Asset
    display: grid
    sort: created_at desc
    limit: 20
    action: asset_detail
    empty: "No assets yet — upload or seed previews"
  review_queue:
    source: Asset
    filter: status = review
    sort: updated_at asc
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"
  pipeline_board:
    source: Asset
    filter: status = draft or status = review or status = approved
    display: kanban
    group_by: status
    sort: updated_at asc
    action: asset_edit
    empty: "No assets in the pipeline"
  status_mix:
    source: Asset
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Asset)
    empty: "No assets yet"

# Goal B media: brand desk is logo + palette identity, then campaigns/assets.
workspace brand_desk "Brand Desk":
  purpose: "Brand media identity — logos and palette swatches above fold, then work queues"
  access: persona(admin, designer)
  # Logo + primary/secondary/accent swatches on each row (media depth).
  # Metrics omitted on purpose: seed-noise period deltas are presentation residual.
  brand_media:
    source: Brand
    display: queue
    sort: name asc
    limit: 25
    action: brand_detail
    empty: "No brands yet"
  campaign_queue:
    source: Campaign
    filter: status = active
    sort: name asc
    display: queue
    empty: "No active campaigns"
  asset_trail:
    source: Asset
    sort: updated_at desc
    limit: 15
    display: timeline
    empty: "No assets yet"
  campaign_mix:
    source: Campaign
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Campaign)
    empty: "No campaigns yet"

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

  recent_feedback:
    source: Feedback
    sort: created_at desc
    limit: 10
    display: timeline
    empty: "No feedback notes yet"

  review_board:
    source: Asset
    filter: status = draft or status = review or status = approved
    display: kanban
    group_by: status
    sort: updated_at asc
    action: asset_edit
    empty: "No assets in the pipeline"

  review_status_mix:
    source: Asset
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Asset)
    empty: "No assets yet"

# Fifth product workspace: campaign desk vs bare campaign list.
# Goal B empty_region_honesty: desk must show live schedule pressure (active
# queue + status board + mix), not multi-panel empty theater when seeds load.
workspace campaign_desk "Campaigns":
  purpose: "Campaign schedule desk — active briefs, status board, brand context"
  access: persona(admin, designer, reviewer)

  campaign_pulse:
    source: Campaign
    display: metrics
    aggregate:
      campaigns: count(Campaign)
      active: count(Campaign where status = active)
      brands: count(Brand)
    tones:
      active: accent

  active_queue:
    source: Campaign
    filter: status = active
    sort: name asc
    limit: 12
    display: queue
    action: campaign_detail
    empty: "No active campaigns"

  all_campaigns:
    source: Campaign
    sort: name asc
    limit: 25
    display: kanban
    group_by: status
    action: campaign_detail
    empty: "No campaigns yet"

  # Work-surface utility (cycle 1483 journey): brand context is pull-to-open, not grid.
  brand_context:
    source: Brand
    sort: name asc
    display: queue
    limit: 12
    action: brand_detail
    empty: "No brands"

  campaign_mix:
    source: Campaign
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Campaign)
    empty: "No campaigns yet"

# Sixth product workspace: feedback trail desk.
workspace feedback_desk "Feedback":
  purpose: "Feedback desk — recent notes on assets in review"
  access: persona(admin, designer, reviewer)

  feedback_pulse:
    source: Feedback
    display: metrics
    aggregate:
      notes: count(Feedback)
      assets: count(Asset)
      in_review: count(Asset where status = review)
    tones:
      notes: accent
      in_review: warning

  recent_notes:
    source: Feedback
    sort: created_at desc
    limit: 25
    display: queue
    empty: "No feedback yet"

  # Work-surface utility: in-review assets are pull work — queue beats grid.
  assets_in_review:
    source: Asset
    filter: status = review
    sort: updated_at asc
    limit: 15
    display: queue
    action: asset_edit
    empty: "Nothing in review"

  note_timeline:
    source: Feedback
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No feedback yet"

  asset_status_mix:
    source: Asset
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Asset)
    empty: "No assets yet"

workspace publish_desk "Publish Desk":
  purpose: "Publish pressure — approved and live assets ready for campaigns"
  access: persona(admin, designer, reviewer)

  publish_pulse:
    source: Asset
    display: metrics
    aggregate:
      approved: count(Asset where status = approved)
      published: count(Asset where status = published)
      active_campaigns: count(Campaign where status = active)
    tones:
      approved: accent
      published: positive
      active_campaigns: positive

  approved_queue:
    source: Asset
    filter: status = approved
    sort: updated_at desc
    limit: 20
    display: queue
    action: asset_edit
    empty: "No approved assets waiting to publish"

  # Live published set is still pull work for campaigns (name order) — queue
  # beats card-grid thrash; hub action stays asset_edit (acceptance cycle 1493).
  published_gallery:
    source: Asset
    filter: status = published
    sort: name asc
    limit: 20
    display: queue
    action: asset_edit
    empty: "No published assets yet — approve and publish from the review path"

  publish_trail:
    source: Asset
    filter: status = published or status = approved
    sort: updated_at desc
    limit: 15
    display: timeline
    action: asset_edit
    empty: "No publish activity yet"

  status_mix:
    source: Asset
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Asset)
    empty: "No assets yet"

workspace draft_studio "Draft Studio":
  purpose: "Draft pressure — work still in draft before review"
  access: persona(admin, designer, reviewer)

  draft_pulse:
    source: Asset
    display: metrics
    aggregate:
      draft: count(Asset where status = draft)
      in_review: count(Asset where status = review)
      brands: count(Brand)
    tones:
      draft: accent
      in_review: warning

  draft_queue:
    source: Asset
    filter: status = draft
    sort: updated_at desc
    limit: 20
    display: queue
    action: asset_edit
    empty: "No draft assets"

  # Work-surface utility: drafts awaiting polish are pull work — queue beats grid.
  draft_gallery:
    source: Asset
    filter: status = draft
    sort: updated_at asc
    limit: 20
    display: queue
    action: asset_edit
    empty: "No draft assets"

  draft_trail:
    source: Asset
    filter: status = draft
    sort: updated_at desc
    limit: 15
    display: timeline
    action: asset_edit
    empty: "No draft activity yet"

  type_mix:
    source: Asset
    filter: status = draft
    display: bar_chart
    group_by: asset_type
    aggregate:
      count: count(Asset)
    empty: "No draft assets to chart"

workspace review_pipeline "Review Pipeline":
  purpose: "In-review asset pressure without warehouse CRUD"
  access: persona(admin, designer, reviewer)

  review_pulse:
    source: Asset
    display: metrics
    aggregate:
      in_review: count(Asset where status = review)
      draft: count(Asset where status = draft)
      approved: count(Asset where status = approved)
    tones:
      in_review: warning
      draft: accent
      approved: positive

  review_queue:
    source: Asset
    filter: status = review
    sort: updated_at asc
    limit: 20
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"

  # Work-surface utility: review pull-work is a queue, not a visual dump.
  review_gallery:
    source: Asset
    filter: status = review
    sort: updated_at asc
    limit: 15
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"

  review_trail:
    source: Asset
    filter: status = review
    sort: updated_at desc
    limit: 15
    display: timeline
    action: asset_edit
    empty: "No review activity yet"

  type_mix:
    source: Asset
    filter: status = review
    display: bar_chart
    group_by: asset_type
    aggregate:
      count: count(Asset)
    empty: "No review assets to chart"

# Goal B empty_region_honesty: live-campaign desk shares Campaign.jsonl seeds.
workspace active_campaigns "Active Campaigns":
  purpose: "Live-campaign pressure — active campaigns without warehouse CRUD"
  access: persona(admin, designer, reviewer)

  campaign_pulse:
    source: Campaign
    display: metrics
    aggregate:
      active: count(Campaign where status = active)
      planning: count(Campaign where status = planning)
      completed: count(Campaign where status = completed)
    tones:
      active: positive
      planning: accent
      completed: muted

  active_queue:
    source: Campaign
    filter: status = active
    sort: start_date desc
    limit: 20
    display: queue
    action: campaign_edit
    empty: "No active campaigns"

  # Work-surface utility: active campaigns are current work — queue beats grid.
  active_grid:
    source: Campaign
    filter: status = active
    sort: name asc
    limit: 15
    display: queue
    action: campaign_edit
    empty: "No active campaigns"

  campaign_trail:
    source: Campaign
    filter: status = active or status = planning
    sort: start_date desc
    limit: 15
    display: timeline
    action: campaign_edit
    empty: "No campaign activity yet"

  status_mix:
    source: Campaign
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Campaign)
    empty: "No campaigns to chart"


surface brand_list "Brands":
  uses entity Brand
  mode: list
  # Dual open: brand hub first, creator second (ST-001 portfolio path).
  open: Brand via id | User via created_by
  section main:
    field name "Name"
    field logo_url "Logo"
    # #1626 P0-8: color widgets render as swatches in list (not raw hex text)
    field primary_color "Primary" widget=color
    field secondary_color "Secondary" widget=color
    field accent_color "Accent" widget=color
    field created_by "Creator"
  ux:
    purpose: "Browse brands with logo thumbs and palette swatches — open brand hub or hop to creator"

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
    field logo_url "Logo"
    field created_by "Creator"
  section palette "Palette":
    layout: strip
    field primary_color "Primary" widget=color
    field secondary_color "Secondary" widget=color
    field accent_color "Accent" widget=color


  # Pull-next asset roster (not status_cards warehouse) — ST-002 journey dig.
  related assets "Assets":
    display: queue
    show: Asset
    columns: name, status, asset_type, quality_score

  # Pull-next campaign roster (not warehouse table) — ST-002 story_walk hub dig.
  related campaigns "Campaigns":
    display: queue
    show: Campaign
    columns: name, status, start_date
  ux:
    purpose: "Brand hub — logo, palette strip, asset queue, and campaign queue"

# Creator hub for brand_list dual-open (Brand|User via created_by) — ST-001 acceptance dig.
surface user_detail "Team member":
  uses entity User
  mode: view
  section identity "Identity":
    field name "Name"
    field email "Email"
    field role "Role"
  section timeline "Timeline":
    field created_at "Joined"
  related brands "Brands authored":
    display: queue
    show: Brand
    columns: name, logo_url, primary_color

  ux:
    purpose: "Team member — brands authored with logo and palette chips"

surface asset_list "Assets":
  uses entity Asset
  mode: list
  # Triple open (journey dig cycle 1596): asset hub, brand palette, creator teammate.
  open: Asset via id | Brand via brand | User via created_by
  section main:
    field name "Name"
    field preview_url "Preview"
    field asset_type "Type"
    field status "Status"
    field brand "Brand"
    field created_by "Created By"
    field tags "Tags"
    field quality_score "Quality"
  ux:
    purpose: "Browse assets with preview thumbs — open a row for the asset, brand, or creator hub"

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
    field preview_url "Preview"
  section production "Production":
    layout: strip
    field asset_type "Type"
    field status "Status"
    field quality_score "Quality"
    field tags "Tags"

  # Feedback as pull queue (rating+comment first) — ST-004/006 story_walk hub dig.
  related feedback "Feedback":
    display: queue
    show: Feedback
    columns: rating, comment, created_at

  ux:
    purpose: "Asset hub — production strip and related feedback queue"

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
  # Triple open (journey dig cycle 1596): note hub, asset hub, reviewer teammate.
  open: Feedback via id | Asset via asset | User via reviewer
  section main:
    field asset "Asset"
    field reviewer "Reviewer"
    field rating "Rating"
    field comment "Comment"
    field created_at "Date"
  ux:
    purpose: "Feedback trail — open a row for the note, asset, or reviewer hub"
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
  # Triple open (journey dig cycle 1596): campaign hub, brand context, creator teammate.
  open: Campaign via id | Brand via brand | User via created_by
  section main:
    field name "Name"
    field brand "Brand"
    field created_by "Created By"
    field status "Status"
    field start_date "Start"
    field end_date "End"
  ux:
    purpose: "Browse campaigns — open a row for the campaign, brand, or creator hub"

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
