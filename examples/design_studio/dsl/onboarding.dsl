module design_studio.guides

use design_studio.core

# Per-persona first-run onboarding for Design Studio.
#   - designer: upload assets and watch for review feedback
#   - reviewer: work the review queue and sign off on assets
# Admins are out of scope. Targets are surfaces; concordance is
# enforced at `dazzle validate` time.

# ─── Designer journey ─────────────────────────────────────────────

guide designer_onboarding "Get your work into the studio":
  audience: persona = designer

  step upload_asset:
    kind: empty_state
    target: surface.asset_list
    title: "Upload your first asset"
    body: "Drop in a logo, icon, or illustration. Pick the brand it belongs to and give it a clear name."
    cta_label: "New Asset"
    cta_target: surface.asset_create
    complete_on: event entity.Asset.created

  step name_it_well:
    kind: popover
    target: surface.asset_create
    title: "Name it so the team can find it"
    body: "A descriptive name and the right brand make an asset easy to search for later."
    placement: bottom
    complete_on: dismiss

  step watch_feedback:
    kind: inline_card
    target: surface.asset_detail
    title: "Watch for review feedback"
    body: "Once an asset is in review, ratings and comments from reviewers show up right on its detail page."
    complete_on: dismiss

  step_order: [upload_asset, name_it_well, watch_feedback]

  on_complete:
    redirect: surface.asset_list

# ─── Reviewer journey ─────────────────────────────────────────────

guide reviewer_onboarding "Work the review queue":
  audience: persona = reviewer

  step review_queue:
    kind: spotlight
    target: surface.asset_list
    title: "Review what's waiting"
    body: "Your Review Desk opens with the awaiting-review queue. Open an asset to see the design and its brand context."
    placement: center
    complete_on: dismiss

  step leave_verdict:
    kind: empty_state
    target: surface.asset_detail
    title: "Leave your verdict"
    body: "Add a rating and a comment so the designer knows what's working and what needs another pass."
    cta_label: "Add Feedback"
    cta_target: surface.feedback_create
    complete_on: event entity.Feedback.created

  step approve_to_publish:
    kind: banner
    target: surface.asset_list
    title: "Approve to publish"
    body: "Once an asset clears the bar, approve it — it moves on to be published for the brand."
    complete_on: dismiss

  step_order: [review_queue, leave_verdict, approve_to_publish]

  on_complete:
    redirect: surface.asset_list
