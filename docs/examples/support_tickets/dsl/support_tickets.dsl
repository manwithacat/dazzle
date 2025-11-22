module support.core

use support.auth

app support_hub "Support Hub"

# --- Domain models -------------------------------------------------------

entity User "User":
  id: uuid pk
  email: email unique
  name: str(120) required
  role: enum[agent,admin,customer]=customer
  current_token: ref AuthToken optional
  created_at: datetime auto_add

entity Ticket "Ticket":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,normal,high,urgent]=normal
  created_by: ref User required
  assigned_to: ref User optional
  created_at: datetime auto_add
  updated_at: datetime auto_update

  index created_by
  index assigned_to
  index status,priority

entity Comment "Comment":
  id: uuid pk
  ticket: ref Ticket required
  author: ref User required
  body: text required
  created_at: datetime auto_add

  index ticket
  index author


# --- Surfaces ------------------------------------------------------------

surface ticket_board "Ticket Board":
  uses entity Ticket
  mode: list

  section filters "Filters":
    field status "Status"
    field priority "Priority"
    field assigned_to "Assigned to"

  section list "Tickets":
    field id "ID"
    field title "Title"
    field status "Status"
    field priority "Priority"
    field created_at "Created"
    field assigned_to "Owner"

  action create_ticket "New ticket":
    on click -> surface ticket_create

  action view_ticket "View ticket":
    on click -> surface ticket_detail


surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create

  section main "Create new ticket":
    field title "Title"
    field description "Description"
    field priority "Priority"

  action submit "Create":
    on submit -> experience ticket_lifecycle step view_created


surface ticket_detail "Ticket Detail":
  uses entity Ticket
  mode: view

  section main "Ticket":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field created_by "Created by"
    field assigned_to "Assigned to"

  section comments "Comments":
    field body "Add comment"

  action assign_to_me "Assign to me":
    on click -> integration agent_tools action assign_to_self

  action add_comment "Add comment":
    on submit -> integration comments_api action create_comment

  action resolve "Mark as resolved":
    on click -> experience ticket_lifecycle step resolve


# --- Simple experiences --------------------------------------------------

experience ticket_lifecycle "Ticket Lifecycle":
  start at step view_created

  step view_created:
    kind: surface
    surface ticket_detail
    on success -> step end

  step resolve:
    kind: surface
    surface ticket_detail
    on success -> step end

  step end:
    kind: surface
    surface ticket_board


# --- Services & foreign models (optional integrations) ------------------

service agent_directory "Agent Directory":
  spec: url "https://internal.example.com/openapi/agents.json"
  auth_profile: jwt_static
  owner: "Internal Platform"

foreign_model AgentProfile from agent_directory "Agent Profile":
  key: id
  constraint read_only

  field id: uuid
  field email: email
  field name: str(120)
  field active: bool

service comments_service "Comments Service":
  spec: url "https://api.example.com/support/comments/openapi.json"
  auth_profile: oauth2_pkce scopes="comments:write"
  owner: "Support Platform"


# --- Integrations --------------------------------------------------------

integration agent_tools "Agent Tools":
  uses service agent_directory
  uses foreign_model AgentProfile

  action assign_to_self:
    when surface ticket_detail submitted
    call agent_directory.get_profile with:
      email <- current_user.email
    map response AgentProfile -> entity Ticket:
      assigned_to <- foreign.id


integration comments_api "Comments API":
  uses service comments_service

  action create_comment:
    when surface ticket_detail submitted
    call comments_service.create_comment with:
      ticket_id <- entity.id
      author_id <- current_user.id
      body <- form.body
