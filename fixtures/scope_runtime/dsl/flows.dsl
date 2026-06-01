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


# #1318 / ADR-0031 — flow-level aggregate invariant. Creates one Posting against
# a transaction and asserts the transaction's postings sum to zero at commit. The
# validator allows only one create per entity per flow, so the flow contributes
# one posting (`amount: input.a`); the test seeds the counter-posting, so the
# invariant fires over the *set* (seeded + created). A balanced set (sum = 0)
# commits; an unbalanced set rolls the whole flow back (400). The invariant locks
# the Transaction anchor FOR UPDATE before aggregating.
atomic balanced_post "Balanced post":
  intent: "Append a posting; the transaction's postings must net to zero"
  permit:
    execute: role(admin)

  input txn: ref Transaction required
  input a: int required

  create Posting:
    transaction: input.txn
    amount: input.a

  invariant: sum(Posting.amount where transaction = input.txn) = 0


# #1317 — strict in-transaction audit. Same department-scoped enrolment as
# `enrol_student`, but `audit: strict` writes the audit row to the
# `_dazzle_atomic_audit` side-table on the flow's own connection, atomic with
# the INSERT: an own-dept enrol commits the audit row WITH the row; a
# foreign-dept enrol is denied (403) and the audit row rolls back too.
atomic enrol_student_strict "Enrol Student (strict audit)":
  intent: "Department-scoped enrolment with strict in-transaction audit"
  permit:
    execute: role(teacher, admin)
  audit: strict

  input label: str(120) required
  input group: ref TeachingGroup required

  create Enrolment:
    label: input.label
    teaching_group: input.group
