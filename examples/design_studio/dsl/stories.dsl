# Journey-bound stories for design_studio agent-first dogfood.
# Warehouse lists alone are not enough — brand/asset hubs + review queue must prove green.

module design_studio.stories

story ST-001 "Designer works portfolio then opens a brand hub":
  status: accepted
  executed_by: surface.brand_list
  persona: designer
  trigger: user_click
  entities: [Brand]
  given:
    - "Designer is on the studio_dashboard workspace"
    - "Brands exist in the portfolio"
  then:
    - "Designer sees portfolio metrics before dense lists"
    - "Opening a brand row hops to the Brand detail hub with assets and campaigns"

story ST-002 "Designer opens brand hub for assets and campaigns":
  status: accepted
  executed_by: surface.brand_detail
  persona: designer
  trigger: user_click
  entities: [Brand, Asset, Campaign]
  given:
    - "Brand exists and is readable"
  then:
    - "Brand hub shows identity, palette strip, related assets and campaigns"

story ST-003 "Reviewer works the review queue on asset catalog":
  status: accepted
  executed_by: surface.asset_edit
  persona: reviewer
  trigger: user_click
  entities: [Asset]
  given:
    - "Reviewer is on the asset_catalog workspace"
    - "Assets exist with status review"
  then:
    - "Review queue surfaces assets awaiting review"
    - "Reviewer can transition an asset from review to approved"

story ST-004 "Reviewer opens asset hub with feedback trail":
  status: accepted
  executed_by: surface.asset_detail
  persona: reviewer
  trigger: user_click
  entities: [Asset, Feedback]
  given:
    - "Asset exists and is readable"
  then:
    - "Asset hub shows production strip and related Feedback"
    - "Reviewer can leave feedback from the asset context"

story ST-005 "Designer hops from asset list to brand context":
  status: accepted
  executed_by: surface.asset_list
  persona: designer
  trigger: user_click
  entities: [Asset, Brand]
  given:
    - "Designer has list permission on Asset"
  then:
    - "Asset rows open Brand via brand (context hub, not orphan warehouse rows)"
    - "Brand hub shows related assets for the batch"

story ST-006 "Designer traces feedback back to the asset hub":
  status: accepted
  executed_by: surface.feedback_list
  persona: designer
  trigger: user_click
  entities: [Feedback, Asset]
  given:
    - "Designer has list permission on Feedback"
  then:
    - "Feedback rows open Asset via asset"
    - "Asset hub shows related Feedback table"
