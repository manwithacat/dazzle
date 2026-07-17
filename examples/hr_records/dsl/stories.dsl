module hr_records.stories

# Journey-bound stories — person career hub + directory, not bare CRUD.

story ST-001 "HR Admin browses staff directory and opens a person hub":
  status: accepted
  executed_by: surface.person_list
  persona: hr_admin
  trigger: user_click
  entities: [Person]
  given:
    - "HR Admin is on the staff_directory workspace"
    - "HR Admin has list permission on Person"
  then:
    - "HR Admin sees headcount metrics and the staff list"
    - "Row open hops to the Person detail hub with employment and salary history"

story ST-002 "Line Manager opens a report career hub":
  status: accepted
  executed_by: surface.person_detail
  persona: manager
  trigger: user_click
  entities: [Person, Employment]
  given:
    - "Manager has list permission on Person for their reports"
  then:
    - "Person hub shows identity, tenure strip, and related employment history"
    - "Manager sees only people in their reporting scope"

story ST-003 "Finance reviews compensation then hops to person context":
  status: accepted
  executed_by: surface.salary_list
  persona: finance
  trigger: user_click
  entities: [Salary, Person]
  given:
    - "Finance is on the compensation_review workspace"
  then:
    - "Finance sees compensation metrics and active salary rows"
    - "Salary row open hops to the Person overview hub via person FK"

story ST-004 "Employee reviews own career timeline hub":
  status: accepted
  executed_by: surface.person_detail
  persona: employee
  trigger: user_click
  entities: [Person, Employment, Salary]
  given:
    - "Employee can read only their own Person record"
  then:
    - "Employee sees own identity, employment history, and salary history on the hub"
    - "Employee cannot see other people"

story ST-005 "HR Admin walks employment history back to the person hub":
  status: accepted
  executed_by: surface.employment_list
  persona: hr_admin
  trigger: user_click
  entities: [Employment, Person]
  given:
    - "HR Admin has list permission on Employment"
  then:
    - "Employment rows open Person via person (context hub, not orphan warehouse rows)"
    - "Person hub shows related employment and compensation tables"
