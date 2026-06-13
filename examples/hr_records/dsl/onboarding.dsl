module hr_records.guides

use hr_records.core

# Per-persona orientation for HR Records.
#   - manager:  read your direct reports' records
#   - finance:  review compensation across the firm
#   - employee: check your own record
# These personas are read-only (hr_admin owns all writes), so the
# guides orient rather than drive create actions. Targets are the
# person directory + detail surfaces only (the org-chart / time-machine
# surfaces are still being built). Concordance enforced at validate.

# ─── Line Manager journey ─────────────────────────────────────────

guide manager_onboarding "See your team's records":
  audience: persona = manager

  step your_team:
    kind: spotlight
    target: surface.person_list
    title: "Your direct reports"
    body: "This list shows the people who report to you. Open anyone to see their role and employment history."
    placement: center
    complete_on: dismiss

  step read_history:
    kind: inline_card
    target: surface.person_detail
    title: "Read the employment history"
    body: "Each person's detail page lays out their current role and how it has changed over time."
    complete_on: dismiss

  step_order: [your_team, read_history]

  on_complete:
    redirect: surface.person_list

# ─── Finance journey ──────────────────────────────────────────────

guide finance_onboarding "Review compensation":
  audience: persona = finance

  step directory:
    kind: spotlight
    target: surface.person_list
    title: "The staff directory"
    body: "Start here to find anyone in the firm, then open their record to review pay."
    placement: center
    complete_on: dismiss

  step salary_and_role:
    kind: inline_card
    target: surface.person_detail
    title: "Read salary and role together"
    body: "A person's detail page shows their compensation history alongside the roles that drove each change."
    complete_on: dismiss

  step_order: [directory, salary_and_role]

  on_complete:
    redirect: surface.person_list

# ─── Employee (self-service) journey ──────────────────────────────

guide employee_onboarding "Check your own record":
  audience: persona = employee

  step your_record:
    kind: spotlight
    target: surface.person_detail
    title: "Your record"
    body: "This is your profile: your role, employment history, and current manager, all in one place."
    placement: center
    complete_on: dismiss

  step keep_accurate:
    kind: inline_card
    target: surface.person_detail
    title: "Keep your details accurate"
    body: "Review your role and salary history. If something looks off, let HR know so they can correct it."
    complete_on: dismiss

  step_order: [your_record, keep_accurate]

  on_complete:
    redirect: surface.person_detail
