module domain_join_co.guides

use domain_join_co.domain

# Per-persona orientation for Domain Join Co.
#   - admin:  verifies the domain + approves joins (in the admin console), and
#             posts announcements to the joined team.
#   - member: the employee who self-joined with a verified company email —
#             reads the team's announcements.
# The verified-domain setup itself (domain connection, join policy, approvals)
# lives in the admin console / `dazzle auth` CLI, not an app surface — see
# docs/reference/verified-domain-join.md. These overlays orient each persona to
# what they do *inside* the workspace. Concordance enforced at validate.

# ─── Workspace Admin journey ──────────────────────────────────────

guide admin_onboarding "Brief your team":
  audience: persona = admin

  step the_board:
    kind: spotlight
    target: surface.announcement_list
    title: "Your team's board"
    body: "Everyone who joined your workspace with a verified company email lands here. This is where you keep them informed."
    placement: center
    complete_on: dismiss

  step post_update:
    kind: inline_card
    target: surface.announcement_create
    title: "Post an update"
    body: "Write an announcement and it appears for every joined member. Domain verification and join approvals live in the admin console."
    complete_on: dismiss

  step_order: [the_board, post_update]

  on_complete:
    redirect: surface.announcement_list

# ─── Team Member journey ──────────────────────────────────────────

guide member_onboarding "Catch up with your team":
  audience: persona = member

  step welcome:
    kind: spotlight
    target: surface.announcement_list
    title: "You're in"
    body: "Your verified company email got you into the workspace. Team Board is your home — announcements from your admin show up here."
    placement: center
    complete_on: dismiss

  step read_one:
    kind: inline_card
    target: surface.announcement_detail
    title: "Open an announcement"
    body: "Tap any item to read it in full — that's where the detail and context live."
    complete_on: dismiss

  step_order: [welcome, read_one]

  on_complete:
    redirect: surface.announcement_list
