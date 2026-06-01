module scope_runtime.domain

# =============================================================================
# scope_runtime — a framework fixture (NOT a user-facing example) that exercises
# the scope-enforcement runtime against a real Postgres:
#
#   - #1311  FK-path (depth-2) `scope: create:` — payload-time SQL probe
#            (`Enrolment.teaching_group.department = current_user.department`)
#   - #1312  `scope: update:` DESTINATION revalidation (repointing an
#            enrolment's group into a foreign department must 404)
#   - #1313  (slice 1b) per-step scope enforcement inside an `atomic` flow
#
# `current_user.department` resolves the same way invoice_ops resolves
# `current_user.tenant_id`: the runtime matches the authenticated email to a
# domain `User` row and merges its scalar columns into AuthContext.preferences.
# =============================================================================

persona teacher "Teacher":
  description: "Department-scoped teacher — sees and mutates only own-department enrolments"
  goals: "Manage own-department enrolments"
  proficiency: intermediate

persona admin "Admin":
  description: "Unscoped administrator"
  goals: "Manage all departments"
  proficiency: expert


entity Department "Department":
  intent: "Scope root — a teaching department"

  id: uuid pk
  name: str(120) required

  permit:
    create: role(admin)
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    create: all
      as: admin
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


entity User "User":
  intent: "Domain user — carries `department` so current_user.department resolves"

  id: uuid pk
  email: email required
  name: str(120) required
  department: ref Department required

  permit:
    create: role(admin)
    read: role(admin)
    list: role(admin)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    list: all
      as: admin


entity TeachingGroup "Teaching Group":
  intent: "Intermediate FK hop — belongs to a department"

  id: uuid pk
  name: str(120) required
  department: ref Department required

  permit:
    create: role(admin)
    read: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    create: all
      as: admin
    read: all
      as: teacher, admin
    list: all
      as: teacher, admin


entity Enrolment "Enrolment":
  intent: "FK-path create-scoped (#1311) + update-destination-guarded (#1312)"

  id: uuid pk
  label: str(120) required
  teaching_group: ref TeachingGroup required
  status: enum[active,ended]=active

  permit:
    create: role(teacher) or role(admin)
    read: role(teacher) or role(admin)
    update: role(teacher) or role(admin)
    list: role(teacher) or role(admin)

  scope:
    # #1311 — depth-2 FK-path create-scope: a teacher may only create an
    # enrolment whose teaching group is in the teacher's own department.
    # Resolved by the payload-time SQL probe against the real DB.
    create: teaching_group.department = current_user.department
      as: teacher
    create: all
      as: admin
    read: teaching_group.department = current_user.department
      as: teacher
    read: all
      as: admin
    list: teaching_group.department = current_user.department
      as: teacher
    list: all
      as: admin
    # #1312 — update destination: repointing `teaching_group` to a group in a
    # foreign department must be rejected (the would-be-final row fails scope).
    update: teaching_group.department = current_user.department
      as: teacher
    update: all
      as: admin
