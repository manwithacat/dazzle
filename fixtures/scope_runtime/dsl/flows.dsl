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
