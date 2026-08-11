# Design Studio — Brand & Design Asset Management
# Exercises: color picker, multi-select, toggle group, context menu,
# rating, slider, rich text, date picker, steps indicator, stat cards

module design_studio.core

app design_studio "Design Studio":
  security_profile: basic
  # App chrome File/Edit-style strip — HM menubar dual-lock in topbar
  # (hyperpart emitter; menus derive from persona nav groups).
  menubar: true

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
    team_desk

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
    team_desk

# ── Entities ─────────────────────────────────────────────────────────

entity User "User":
  display_field: name
  id: uuid pk
  email: str(200) unique required pii(category=contact)
  name: str(100) required pii(category=identity)
  role: enum[admin,designer,reviewer]=designer
  # Goal B org_structure (cycle 1865): department + job title so Team desk shows
  # Creative Ops / Design Systems / Brand Strategy / Review QA shape — not a flat
  # persona-only roster (peer creative tools: Figma / Adobe / Abstract / Frame.io).
  department: str(50)
  job_title: str(80)
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

  # Goal B media peer-pack (cycle 1923): Figma / Bynder / Frontify put logo +
  # palette swatches on brand identity rows — not name-only brand queues.
  fitness:
    repr_fields: [name, logo_url, primary_color, secondary_color, accent_color]

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
  # Optional campaign assignment — campaign hub pulls creatives (acceptance dig).
  campaign: ref Campaign
  name: str(200) required
  description: text
  asset_type: enum[logo,icon_glyph,illustration,photo,pattern,typography]=logo
  status: enum[draft,review,approved,published,archived]=draft
  # Goal B media peer-pack (cycle 1912): Figma / Frame.io / Bynder put revision
  # number + approval stamp on creative work — not status-only meta.
  version: int=1
  approved_at: datetime optional
  # Goal B media: HTTPS preview thumb on catalog cards (file binary stays optional).
  preview_url: url
  file: file
  tags: str(500)
  quality_score: int
  created_by: ref User
  created_at: datetime auto_add
  updated_at: datetime auto_update

  fitness:
    repr_fields: [name, version, status, asset_type, brand]

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
  # Goal B conversation: peer review tools (Figma/Abstract) show critique copy
  # as the row identity — not a UUID shell. display_field drives queue titles.
  intent: "Threaded review critique on a Design Asset — the conversation that moves draft to approved"
  domain: design
  patterns: messaging, audit_trail
  display_field: comment
  id: uuid pk
  asset: ref Asset required
  reviewer: ref User required
  rating: int
  comment: text required
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

  fitness:
    repr_fields: [asset, reviewer, comment, rating]


# Goal B document composition: named design briefs/guides buyers scan above critique trail.
entity DesignDocument "Design Document":
  intent: "A named design document — brief, brand guide, art direction, creative spec, or decision log buyers scan above the critique trail"
  domain: design
  patterns: documentation, audit_trail
  display_field: headline
  id: uuid pk
  brand: ref Brand required
  headline: str(200) required
  doc_kind: enum[brief, brand_guide, art_direction, creative_spec, decision]=brief
  body: text
  status: enum[draft, published, archived]=draft
  author: str(120)
  created_at: datetime auto_add

  # Domain residual status∄transitions (cycle 1845): design briefs publish then archive.
  transitions:
    draft -> published: role(admin) or role(designer)
    published -> archived: role(admin) or role(designer)
    draft -> archived: role(admin)
    published -> draft: role(admin)

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

  fitness:
    repr_fields: [brand, headline, doc_kind, status, author]

# ── Workspaces ───────────────────────────────────────────────────────

# Story-driven: designer home = studio_dashboard; reviewer often uses review_desk
# (docs/guides/story-to-composition.md). Goal B media home: peer creative tools
# (Figma / Adobe / Bynder) put recent creatives as pixels on the portfolio home —
# not metrics + critique meta first.
workspace studio_dashboard "Studio Dashboard":
  access: persona(admin, designer, reviewer)
  # Goal B media + command_density (cycle 1836): pixels first, then dual
  # attention (review + draft) before critique trail — peer creative ops dens
  # (Figma/Abstract/Frame.io) put multi-panel pressure above discussion.
  purpose: "Multi-panel studio home — media shelf, dual attention, design docs, then critique trail"
  # Goal B media home FIRST — portfolio is a visual shelf (preview_url thumbs).
  media_shelf:
    source: Asset
    display: grid
    sort: updated_at desc
    # Cap 2 so dual attention (review+draft) shares the above-fold command dens
    # with media home (cycle 1836 command_density still proof).
    limit: 2
    action: asset_detail
    empty: "No assets yet — seed or upload previews"
  # Compact load strip after pixels (no delta-theater tile wall).
  portfolio:
    source: Asset
    display: metrics
    aggregate:
      assets: count(Asset)
      in_review: count(Asset where status = review)
      drafts: count(Asset where status = draft)
      brands: count(Brand)
      documents: count(DesignDocument)
      conversation: count(Feedback)
    tones:
      in_review: warning
      drafts: accent
      documents: accent
      conversation: accent
  # Dual attention — in-review + draft pressure above fold (tight caps for fold).
  review_pressure:
    source: Asset
    filter: status = review
    sort: updated_at asc
    limit: 3
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"
  draft_pressure:
    source: Asset
    filter: status = draft
    sort: updated_at desc
    limit: 2
    display: queue
    action: asset_edit
    empty: "No drafts in flight"
  # Dual attention B — Goal B document composition on Studio home.
  # Named design briefs/guides (display_field: headline) before the critique trail.
  composition:
    source: DesignDocument
    sort: created_at desc
    limit: 3
    display: queue
    action: design_document_detail
    empty: "No design documents yet — attach a brief or brand guide on a brand hub"

  # Critique trail after dual attention + docs — reply secondary to pressure queues.
  live_conversation:
    source: Feedback
    sort: created_at desc
    limit: 3
    display: queue
    action: feedback_detail
    empty: "No critique yet — reviewer notes on your assets appear here"
  # Pull-to-open brand hubs (capped so meta cannot eat the fold).
  brands:
    source: Brand
    display: queue
    sort: name asc
    limit: 4
    action: brand_detail
    empty: "No brands yet"
  ux:
    as designer:
      purpose: "Multi-panel media home — thumbs, dual attention, docs, then critique"
      focus: media_shelf, portfolio, review_pressure, draft_pressure, composition, live_conversation
    as admin:
      purpose: "Multi-panel studio ops — media, dual attention, docs, brands, then critique"
      focus: media_shelf, portfolio, review_pressure, draft_pressure, composition, brands, live_conversation
    as reviewer:
      purpose: "Multi-panel review home — creatives, dual attention, docs, then critique"
      focus: media_shelf, portfolio, review_pressure, draft_pressure, composition, live_conversation

# Goal B media (cycle 1734): catalog is a visual media shelf — asset preview
# thumbs must win the fold. Peer tools (Bynder / Frontify / Adobe CC) put
# pixels first; brand meta is secondary context, not a four-row palette wall.
workspace asset_catalog "Asset Catalog":
  purpose: "Media shelf — asset preview thumbs above fold, then compact brand palette (no metric delta theater)"
  access: persona(admin, designer, reviewer)
  # Visual media grid FIRST — preview_url thumbs + type · name titles.
  media_grid:
    source: Asset
    display: grid
    sort: created_at desc
    limit: 12
    action: asset_detail
    empty: "No assets yet — upload or seed previews"
  # Goal B media recipe brand_swatch_wall (cycle 1923): Brand entity-fallback
  # columns include logo + Primary/Secondary/Accent color types (salience keeps
  # palette chips) so DAM buyers scan swatches after creatives — not name shells.
  brand_palette:
    source: Brand
    display: queue
    sort: name asc
    limit: 4
    action: brand_detail
    empty: "No brands yet — seed palette swatches on brand records"
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
  # Goal B empty_region_honesty (cycle 1856): host bar_chart dogfood under fold
  # on the DAM catalog (not on every secondary pressure desk).
  status_mix:
    source: Asset
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Asset)
    empty: "No assets yet"
  # Timeline dogfood under fold — secondary desks stay pulse+queues only.
  recent_activity:
    source: Asset
    sort: updated_at desc
    limit: 12
    display: timeline
    action: asset_detail
    empty: "No asset activity yet"
  ux:
    as designer:
      purpose: "See asset preview thumbs above fold before brand palette"
      focus: media_grid, brand_palette, review_queue
    as admin:
      purpose: "Media shelf first — previews, then brand identity"
      focus: media_grid, brand_palette, review_queue
    as reviewer:
      purpose: "Scan creatives as pixels before brand meta"
      focus: media_grid, brand_palette, review_queue

# Goal B media: brand desk is asset media shelf first, then brand swatch wall.
# empty_region_honesty (cycle 1856): drop asset_trail + campaign_mix thrash —
# bar_chart/timeline dogfood lives on asset_catalog under fold.
# Recipe brand_swatch_wall (cycle 1923): peer Figma/Bynder put Primary/Secondary/
# Accent chips next to logo identity — not a name-only brand queue.
workspace brand_desk "Brand Desk":
  purpose: "Brand media identity — asset preview thumbs above fold, then palette swatch wall and campaigns"
  access: persona(admin, designer)
  # Goal B media shelf FIRST — logo/photo creatives as preview thumbs (pixels win).
  # Cap 2 so palette swatch wall (Primary/Secondary/Accent) shares the fold
  # after cycle 1923 brand_swatch_wall peer upgrade (not a full-fold media dump).
  asset_media:
    source: Asset
    filter: asset_type = logo or asset_type = photo or asset_type = illustration
    sort: created_at desc
    limit: 2
    display: grid
    action: asset_detail
    empty: "No logo or photo assets yet"
  # Brand swatch wall IMMEDIATELY after pixels — entity-fallback Brand columns
  # keep logo + Primary/Secondary/Accent color types (compact fold cap).
  # Metrics omitted on purpose: seed-noise period deltas are presentation residual.
  brand_media:
    source: Brand
    display: queue
    sort: name asc
    limit: 3
    action: brand_detail
    title: "Palette Swatches"
    empty: "No brand swatches yet — add logo + palette colors on brand records"
  # Hyperpart emitter dogfood: display: carousel → Carousel (.dz-carousel).
  # After fold pair (asset_media + brand_media) so swatches stay buyer-visible.
  asset_carousel:
    source: Asset
    filter: asset_type = logo or asset_type = photo or asset_type = illustration
    sort: created_at desc
    limit: 4
    display: carousel
    empty: "No media slides yet"
  campaign_queue:
    source: Campaign
    filter: status = active
    sort: name asc
    display: queue
    empty: "No active campaigns"
  ux:
    as designer:
      purpose: "Asset media previews above fold before palette swatch wall and campaigns"
      focus: asset_media, brand_media, campaign_queue
    as admin:
      purpose: "Creative previews first, then brand palette swatches and campaign schedule"
      focus: asset_media, brand_media, campaign_queue

workspace review_desk "Review Desk":
  # Goal B command_density (cycle 1836): dual attention (awaiting + drafts)
  # before conversation trail. Conversation still present — after pressure queues
  # so buyer stills show multi-panel review ops (peer: Figma/Abstract review dens).
  purpose: "Multi-panel review — dual attention, design docs, then live critique trail"
  access: persona(admin, designer, reviewer)
  review_load:
    source: Asset
    display: metrics
    aggregate:
      in_review: count(Asset where status = review)
      draft: count(Asset where status = draft)
      approved: count(Asset where status = approved)
      documents: count(DesignDocument)
      conversation: count(Feedback)
    tones:
      in_review: warning
      approved: positive
      documents: accent
      conversation: accent

  # Dual attention — in-review + draft pressure above fold (tight caps so both
  # queues share the viewport with metrics — cycle 1836 still proof).
  awaiting_review:
    source: Asset
    filter: status = review
    sort: updated_at asc
    limit: 2
    display: queue
    action: asset_edit
    empty: "Nothing awaiting review"
  draft_queue:
    source: Asset
    filter: status = draft
    sort: updated_at desc
    limit: 2
    display: queue
    action: asset_edit
    empty: "No drafts waiting to enter review"

  # Goal B document composition after dual attention — named briefs before critique.
  composition:
    source: DesignDocument
    sort: created_at desc
    limit: 3
    display: queue
    action: design_document_detail
    empty: "No design documents yet — attach a brief or brand guide on a brand hub"

  # Goal B conversation spine after dual attention + docs — domain-true critique copy.
  live_conversation:
    source: Feedback
    sort: created_at desc
    limit: 3
    display: queue
    action: feedback_detail
    empty: "No conversation yet — reviewer notes appear here as assets move through review"

  recently_approved:
    source: Asset
    filter: status = approved
    sort: updated_at desc
    limit: 3
    display: queue
    empty: "No recent approvals"
  review_board:
    source: Asset
    filter: status = draft or status = review or status = approved
    display: kanban
    group_by: status
    sort: updated_at asc
    action: asset_edit
    empty: "No assets in the pipeline"

  ux:
    as reviewer:
      purpose: "Multi-panel review — dual attention + docs before critique trail"
      focus: review_load, awaiting_review, draft_queue, composition, live_conversation
    as designer:
      purpose: "Multi-panel review — dual attention + docs before critique trail"
      focus: review_load, awaiting_review, draft_queue, composition, live_conversation
    as admin:
      purpose: "Multi-panel review ops — dual attention + docs before critique trail"
      focus: review_load, awaiting_review, draft_queue, composition, live_conversation

# Fifth product workspace: campaign desk vs bare campaign list.
# Goal B media (cycle 1803): peer creative ops (Frame.io / Bynder / Adobe) put
# campaign creatives as pixels on the schedule desk — not only briefs + charts.
# Empty_region still holds: seeded assigned creatives + active queue fill fold.
workspace campaign_desk "Campaigns":
  purpose: "Campaign media desk — assigned creative preview thumbs above fold, then schedule pressure"
  access: persona(admin, designer, reviewer)

  # Creative wall FIRST — preview_url thumbs for assets assigned to campaigns.
  campaign_creatives:
    source: Asset
    filter: campaign != null
    sort: updated_at desc
    limit: 10
    display: grid
    action: asset_detail
    empty: "No creatives assigned to campaigns yet — link assets from the asset hub"

  campaign_pulse:
    source: Campaign
    display: metrics
    aggregate:
      campaigns: count(Campaign)
      active: count(Campaign where status = active)
      creatives: count(Asset where campaign != null)
      brands: count(Brand)
    tones:
      active: accent
      creatives: positive

  active_queue:
    source: Campaign
    filter: status = active
    sort: name asc
    limit: 10
    display: queue
    action: campaign_detail
    empty: "No active campaigns"

  all_campaigns:
    source: Campaign
    sort: name asc
    limit: 20
    display: kanban
    group_by: status
    action: campaign_detail
    empty: "No campaigns yet"

  # Brand context with palette swatches via entity-fallback columns
  # (pull-to-open; creatives keep fold priority).
  brand_context:
    source: Brand
    sort: name asc
    display: queue
    limit: 8
    action: brand_detail
    empty: "No brands"

  ux:
    as designer:
      purpose: "Campaign creatives as pixels first — schedule briefs after the media wall"
      focus: campaign_creatives, campaign_pulse, active_queue, all_campaigns
    as admin:
      purpose: "Media-first campaign desk — assigned thumbs, then schedule pressure"
      focus: campaign_creatives, campaign_pulse, active_queue, all_campaigns
    as reviewer:
      purpose: "See campaign creatives before status boards"
      focus: campaign_creatives, campaign_pulse, active_queue, all_campaigns

# Sixth product workspace: feedback trail desk.
# empty_region_honesty (cycle 1856): pulse + conversation + in-review queue —
# not twin note timeline + asset status bar dump (bar/timeline on asset_catalog).
workspace feedback_desk "Feedback":
  purpose: "Critique trail — conversation on assets in review, not a warehouse dump of notes"
  access: persona(admin, designer, reviewer)

  feedback_pulse:
    source: Feedback
    display: metrics
    aggregate:
      conversation: count(Feedback)
      assets: count(Asset)
      in_review: count(Asset where status = review)
    tones:
      conversation: accent
      in_review: warning

  # Conversation spine on the dedicated feedback desk (same queue identity).
  live_conversation:
    source: Feedback
    sort: created_at desc
    limit: 25
    display: queue
    action: feedback_detail
    empty: "No conversation yet — add a critique from an asset hub"

  # Work-surface utility: in-review assets are pull work — queue beats grid.
  assets_in_review:
    source: Asset
    filter: status = review
    sort: updated_at asc
    limit: 15
    display: queue
    action: asset_edit
    empty: "Nothing in review"

# empty_region_honesty (cycle 1856): publish pressure = pulse + dual queues only.
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

# empty_region_honesty (cycle 1856): one draft queue + metrics — not twin gallery/trail/bar.
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

# empty_region_honesty (cycle 1856): one review queue + metrics — not twin gallery/trail/bar.
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

# Goal B empty_region_honesty: live-campaign desk = pulse + one active queue
# (cycle 1856 — no twin grid / trail / status bar; bar/timeline on asset_catalog).
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

# Goal B org_structure (cycle 1865): peer creative-ops tools (Figma / Adobe /
# Abstract / Frame.io / Bynder) show studio staff by discipline and department
# before a flat people dump — admins reassign and reviewers find owners from
# org shape, not a three-row persona roster.
workspace team_desk "Team":
  purpose: "Org structure for the studio — title and department before flat roster and brand load"
  access: persona(admin, designer, reviewer)

  team_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      brands: count(Brand)
      in_review: count(Asset where status = review)
    tones:
      people: accent
      in_review: warning

  # Title board — Studio Admin / Art Director / Brand Designer / …
  by_title:
    source: User
    display: kanban
    group_by: job_title
    sort: name asc
    limit: 40
    action: user_detail
    empty: "No titled studio staff yet"

  # Department placement — Creative Ops / Design Systems / Brand Strategy / Review QA.
  by_department:
    source: User
    display: queue
    sort: department asc, name asc
    limit: 40
    action: user_detail
    empty: "No staff placed in departments yet"

  # Secondary flat roster (after hierarchy).
  people:
    source: User
    display: queue
    sort: department asc, name asc
    limit: 25
    action: user_detail
    empty: "No users yet"

  # Brand load after org shape — who owns brands, not before hierarchy.
  brand_load:
    source: Brand
    sort: name asc
    limit: 15
    display: queue
    action: brand_detail
    empty: "No brands yet"

  org_hint:
    display: status_list
    entries:
      - title: "By title board"
        caption: "Art Director / Brand Designer / Systems Lead / Reviewer columns show who can act"
        icon: "users"
        state: accent
      - title: "Department queue"
        caption: "Creative Ops / Design Systems / Brand Strategy / Review QA before flat roster"
        icon: "building-2"
        state: positive
      - title: "Brand load last"
        caption: "Brand hubs after you read org shape"
        icon: "palette"
        state: warning

  ux:
    as admin:
      purpose: "See studio staff by title and department before brand load"
      focus: team_pulse, by_title, by_department, people
    as designer:
      purpose: "Org structure for creative ops — role board then department"
      focus: team_pulse, by_title, by_department, people
    as reviewer:
      purpose: "Read team org shape before brand and review pressure"
      focus: team_pulse, by_title, by_department, people


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
  # Goal B media peer-pack (cycle 1912): version on creative rows.
  related assets "Assets":
    display: queue
    show: Asset
    columns: name, version, status, asset_type, quality_score

  # Pull-next campaign roster (not warehouse table) — ST-002 story_walk hub dig.
  related campaigns "Campaigns":
    display: queue
    show: Campaign
    columns: name, status, start_date

  # Goal B document: named briefs / brand guides on the brand hub.
  related documents "Documents":
    display: queue
    show: DesignDocument
    columns: headline, doc_kind, status, author

  ux:
    purpose: "Brand hub — logo, palette strip, assets, campaigns, and design documents"

# Org roster for Team desk + dual-open creator hubs (Brand|User via created_by).
surface user_list "Team":
  uses entity User
  mode: list
  section main:
    field name "Name"
    field email "Email"
    field role "Role"
    field job_title "Job Title"
    field department "Department"
  ux:
    purpose: "Browse studio staff by title and department"
    sort: department asc, name asc
    filter: department, job_title, role
    search: name, email, department, job_title

# Creator hub for brand_list dual-open (Brand|User via created_by) — ST-001 acceptance dig.
surface user_detail "Team member":
  uses entity User
  mode: view
  section identity "Identity":
    field name "Name"
    field email "Email"
    field role "Role"
    field job_title "Job Title"
    field department "Department"
  section timeline "Timeline":
    field created_at "Joined"
  related brands "Brands authored":
    display: queue
    show: Brand
    columns: name, logo_url, primary_color, secondary_color, accent_color

  ux:
    purpose: "Team member — org placement, brands authored with logo and palette chips"

surface asset_list "Assets":
  uses entity Asset
  mode: list
  # Triple open (journey dig cycle 1596): asset hub, brand palette, creator teammate.
  open: Asset via id | Brand via brand | User via created_by
  section main:
    field name "Name"
    field preview_url "Preview"
    field asset_type "Type"
    field version "Version"
    field status "Status"
    field approved_at "Approved"
    field brand "Brand"
    field created_by "Created By"
    field tags "Tags"
    field quality_score "Quality"
  ux:
    purpose: "Browse assets with preview thumbs, revision, and approval stamp — open asset, brand, or creator"

surface asset_create "New Asset":
  uses entity Asset
  mode: create
  section details:
    field name "Asset Name"
    field description "Description" widget=rich_text
    field brand "Brand" widget=combobox
    field campaign "Campaign" widget=combobox
    field asset_type "Type"
    field version "Version"
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
    field campaign "Campaign"
    field preview_url "Preview"
  section production "Production":
    layout: strip
    field asset_type "Type"
    field version "Version"
    field status "Status"
    field approved_at "Approved At"
    field quality_score "Quality"
    field tags "Tags"

  # Feedback as pull queue (rating+comment first) — ST-004/006 story_walk hub dig.
  related feedback "Feedback":
    display: queue
    show: Feedback
    columns: rating, comment, created_at

  ux:
    purpose: "Asset hub — revision + approval stamp on production strip, then feedback queue"

surface asset_edit "Edit Asset":
  uses entity Asset
  mode: edit
  section details:
    field name "Name"
    field description "Description" widget=rich_text
    field campaign "Campaign" widget=combobox
    field version "Version"
    field tags "Tags" widget=tags
    field quality_score "Quality" widget=slider
    field status "Status"
    field approved_at "Approved At"

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
    field created_by "Owner"
  section schedule "Schedule":
    layout: strip
    field status "Status"
    field start_date "Start"
    field end_date "End"
    field budget "Budget"

  # Goal B media: preview_url first so hub rows read as creatives, not name shells.
  # (related display modes: table|status_cards|file_list|queue — not workspace grid)
  related assets "Campaign assets":
    display: status_cards
    show: Asset
    columns: preview_url, name, version, status, asset_type

  ux:
    purpose: "Campaign hub — schedule strip and assigned creative cards with previews"

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
    # Comment first — conversation identity (display_field) before meta.
    field comment "Critique"
    field asset "Asset"
    field reviewer "Reviewer"
    field rating "Rating"
    field created_at "Date"
  ux:
    purpose: "Conversation trail — open a critique note, the parent asset, or the reviewer hub"
    sort: created_at desc
    filter: asset, reviewer
    empty: "No conversation yet — critique notes appear here as review moves"

# View surface so ST-004 story_coverage sees Feedback.view for reviewer
# (related table alone was not enough for discovery coherence).
# open: is list-only (#1603) — hop to parent is via asset field + list open.
surface feedback_detail "Feedback Detail":
  uses entity Feedback
  mode: view
  section summary "Critique":
    layout: strip
    field comment "Critique"
    field rating "Rating"
    field asset "Asset"
    field reviewer "Reviewer"
    field created_at "Date"
  ux:
    purpose: "Read the critique in context of the parent asset — conversation hub, not a form dump"

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


# DesignDocument surfaces (Goal B document composition)
surface design_document_list "Design Documents":
  uses entity DesignDocument
  mode: list
  render: fragment
  open: DesignDocument via id | Brand via brand

  section main "Documents":
    field headline "Headline"
    field doc_kind "Kind"
    field brand "Brand"
    field status "Status"
    field author "Author"
    field created_at "When"

  ux:
    purpose: "Document composition queue — named briefs and brand guides; open a letter hub or hop to the Brand"
    sort: created_at desc
    filter: doc_kind, status
    search: headline, body
    empty: "No design documents yet — open a brand hub to attach a brief or brand guide"

surface design_document_create "Add Design Document":
  uses entity DesignDocument
  mode: create
  render: fragment
  section main "New document":
    field brand "Brand"
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"
  ux:
    purpose: "Attach a named brief, brand guide, art direction, or decision log to a brand"

surface design_document_detail "Design Document":
  uses entity DesignDocument
  mode: view
  render: fragment

  section summary "Document":
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field brand "Brand"
    field author "Author"
    field created_at "When"

  section body "Body":
    field body "Body"

  ux:
    purpose: "Design document hub — named letter, lifecycle strip, brand, and body in one place"

surface design_document_edit "Edit Design Document":
  uses entity DesignDocument
  mode: edit
  render: fragment
  section main "Edit document":
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"
  ux:
    purpose: "Update design document headline, kind, or status"
