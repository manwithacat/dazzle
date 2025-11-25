# Module declaration
module support_tickets.core

# Application definition
app support_tickets "Support Tickets"

# User entity - represents system users
entity User "User":
  id: uuid pk

  # 'unique' ensures no duplicate emails in the database
  email: str(255) required unique
  name: str(200) required
  created_at: datetime auto_add

# Ticket entity - represents support tickets
# Demonstrates relationships with other entities
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  description: text required

  # Enum fields with default values
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium

  # Foreign key relationships using ref EntityName
  # 'required' means the ticket must have a creator
  created_by: ref User required

  # Optional reference - tickets can be unassigned
  assigned_to: ref User

  created_at: datetime auto_add
  updated_at: datetime auto_update

# Comment entity - demonstrates many-to-one relationships
# Multiple comments can belong to one ticket
entity Comment "Comment":
  id: uuid pk

  # This comment belongs to a ticket (many-to-one)
  ticket: ref Ticket required

  # This comment was written by a user (many-to-one)
  author: ref User required

  content: text required
  created_at: datetime auto_add

# ============================================================================
# USER SURFACES
# ============================================================================

# List surface - displays all users
surface user_list "User List":
  uses entity User
  mode: list

  section main "Users":
    field email "Email"
    field name "Name"
    field created_at "Created"

# Detail/view surface - shows user information
surface user_detail "User Detail":
  uses entity User
  mode: view

  section main "User Details":
    field email "Email"
    field name "Name"
    field created_at "Created"

# Create surface - add new user
surface user_create "Create User":
  uses entity User
  mode: create

  section main "New User":
    field email "Email"
    field name "Name"

# Edit surface - update user information
surface user_edit "Edit User":
  uses entity User
  mode: edit

  section main "Edit User":
    field email "Email"
    field name "Name"

# ============================================================================
# TICKET SURFACES
# ============================================================================

# List surface - displays all tickets
surface ticket_list "Ticket List":
  uses entity Ticket
  mode: list

  section main "Support Tickets":
    field title "Title"
    field status "Status"
    field priority "Priority"
    # Foreign key fields display related object's string representation
    field created_by "Created By"
    field created_at "Created"

# Detail/view surface - shows all ticket information
surface ticket_detail "Ticket Detail":
  uses entity Ticket
  mode: view

  section main "Ticket Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field created_by "Created By"
    field assigned_to "Assigned To"
    field created_at "Created"
    field updated_at "Updated"

# Create surface - note that created_by is typically set automatically
# in real applications (from current user), not shown in the form
surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create

  section main "New Ticket":
    field title "Title"
    field description "Description"
    field priority "Priority"

# Edit surface - allows updating ticket details and assignment
surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit

  section main "Edit Ticket":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    # Reassigning is common in support ticket workflows
    field assigned_to "Assigned To"

# ============================================================================
# COMMENT SURFACES
# ============================================================================

# List surface - displays all comments
surface comment_list "Comment List":
  uses entity Comment
  mode: list

  section main "Comments":
    field ticket "Ticket"
    field author "Author"
    field content "Content"
    field created_at "Created"

# Detail/view surface - shows comment information
surface comment_detail "Comment Detail":
  uses entity Comment
  mode: view

  section main "Comment Details":
    field ticket "Ticket"
    field author "Author"
    field content "Content"
    field created_at "Created"

# Create surface - add new comment
surface comment_create "Create Comment":
  uses entity Comment
  mode: create

  section main "New Comment":
    field ticket "Ticket"
    field author "Author"
    field content "Content"

# Edit surface - update comment
surface comment_edit "Edit Comment":
  uses entity Comment
  mode: edit

  section main "Edit Comment":
    field content "Content"
