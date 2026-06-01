module scope_runtime.surfaces

use scope_runtime.domain

surface enrolment_list "Enrolments":
  uses entity Enrolment
  mode: list
  section main:
    field label "Label"
    field status "Status"

surface enrolment_create "New Enrolment":
  uses entity Enrolment
  mode: create
  section main:
    field label "Label"
    field teaching_group "Group"

surface enrolment_edit "Edit Enrolment":
  uses entity Enrolment
  mode: edit
  section main:
    field label "Label"
    field teaching_group "Group"
    field status "Status"
