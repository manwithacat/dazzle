# Stem: Story-driven job workspaces (design_studio)

## Claim

Designers work brand/portfolio desks; reviewers land on the review queue — not
a shared asset warehouse.

## Reconstruct

- designer default: `studio_dashboard` = media home (preview thumbs) + compact load + critique.
- designer also has `brand_desk` (brand-first path).
- reviewer default: `review_desk` = review-load + awaiting-review queue.
- `asset_catalog` is the media shelf (preview thumbs first, then brand palette)
  for all product personas — pixels above brand meta (Goal B media).
- Brand hub related **assets** and **campaigns** are **pull queues**
  (assets: name+status+type; campaigns: name+status) — not status_cards/tables.
- Asset hub feedback is a **pull queue** (rating+comment) — not warehouse tables.
- List triple-open (journey dig cycle 1596): `asset_list` → Asset|Brand|User(created_by);
  `feedback_list` → Feedback|Asset|User(reviewer); `campaign_list` →
  Campaign|Brand|User(created_by) — hub first, parent then teammate context.
- List dual-open (acceptance dig): `brand_list` → Brand|User via `created_by`
  (brand hub first, creator context second).
- Campaign desk (`campaign_desk`) shows schedule pressure; opening a campaign
  lands a **hub** with schedule strip + brand + **assigned creative queue**
  (`Asset.campaign` optional FK) — ST-007 acceptance dig (not field dump only).

## Not this

- Persona lands on a bare entity list when the job is triage, review, or oversight.
- Every persona defaults to the same mega-workspace.
- Story `given:` workspace names that disagree with `default_workspace`.
- Hub related rosters as dense tables when the job is pull-next review.
- Asset/campaign list hops **only** to parent Brand (orphan brand-only open).

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
- Product maturity: `scripts/example_product_maturity.py`
