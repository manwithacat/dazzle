# Multiple entities with references
module corpus.multi_entity
app multi_entity "Multi-Entity App"

entity Company "Company":
  id: uuid pk
  name: str(200) required
  industry: str(100) optional

entity Person "Person":
  id: uuid pk
  first_name: str(100) required
  last_name: str(100) required
  email: email required
  company: ref Company optional
  role: enum[employee,contractor,intern]=employee

entity Project "Project":
  id: uuid pk
  title: str(200) required
  description: text optional
  lead: ref Person required
  company: ref Company required
  status: enum[planning,active,completed,cancelled]=planning
  budget: decimal(12,2) optional

surface company_list "Companies":
  uses entity Company
  mode: list
  section main:
    field name "Company Name"
    field industry "Industry"

surface person_list "People":
  uses entity Person
  mode: list
  section main:
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field company "Company"
    field role "Role"

surface project_list "Projects":
  uses entity Project
  mode: list
  section main:
    field title "Project"
    field lead "Lead"
    field company "Company"
    field status "Status"
