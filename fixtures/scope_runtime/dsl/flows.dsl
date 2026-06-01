module scope_runtime.flows


# Atomic flow exercising #1313 slice 1b: per-step `scope: create:` enforcement.
# Creating an Enrolment inside the flow must satisfy Enrolment's FK-path
# create-scope (`teaching_group.department = current_user.department`), resolved
# by an in-transaction probe. A teacher enrolling into an own-department group
# succeeds; a foreign-department group is denied (403) and the whole flow rolls
# back.
atomic enrol_student "Enrol Student":
  intent: "Create a department-scoped enrolment in one transaction"
  permit:
    execute: role(teacher, admin)

  input label: str(120) required
  input group: ref TeachingGroup required

  create Enrolment:
    label: input.label
    teaching_group: input.group


# Atomic flow exercising #1313 update-step execution + scope: update: (source +
# destination) in-transaction. Reassigning an enrolment to a group is allowed
# only when BOTH the existing row (source) and the would-be-final row
# (destination) are in the teacher's department; otherwise 404 + rollback.
atomic reassign_enrolment "Reassign Enrolment":
  intent: "Move an enrolment to a different teaching group, scope-guarded"
  permit:
    execute: role(teacher, admin)

  input enrolment: ref Enrolment required
  input group: ref TeachingGroup required

  update Enrolment(input.enrolment):
    teaching_group: input.group
