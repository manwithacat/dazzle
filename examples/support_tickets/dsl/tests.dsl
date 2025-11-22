# Test Definitions for Support Tickets System
# These tests define domain-specific validation beyond standard CRUD

# =============================================================================
# USER TESTS
# =============================================================================

test user_email_uniqueness:
  """Test that duplicate emails are rejected."""
  setup:
    user1: create User with email="test@example.com", name="User One"
  action: create User
  data:
    email: "test@example.com"
    name: "User Two"
  expect:
    status: error
    error_message contains "email already exists"

test user_email_validation:
  """Test that invalid emails are rejected."""
  action: create User
  data:
    email: "not-an-email"
    name: "Test User"
  expect:
    status: error
    error_message contains "invalid email"

# =============================================================================
# TICKET TESTS
# =============================================================================

test ticket_creation_with_defaults:
  """Test ticket creation uses correct default values."""
  setup:
    creator: create User with email="user@example.com", name="Creator"
  action: create Ticket
  data:
    title: "Test Ticket"
    description: "Test description"
    created_by: creator
  expect:
    status: success
    created: true
    field status equals "open"
    field priority equals "medium"

test ticket_auto_population:
  """Test that created_by is auto-populated when not provided."""
  action: create Ticket
  data:
    title: "Auto-populated Ticket"
    description: "Testing auto-population"
    priority: "high"
  expect:
    status: success
    created: true
    field created_by not_equals null

test ticket_assignment_workflow:
  """Test assigning an unassigned ticket to a user."""
  setup:
    creator: create User with email="creator@example.com", name="Creator"
    assignee: create User with email="dev@example.com", name="Developer"
    ticket: create Ticket with title="Unassigned", description="Test", created_by=creator
  action: update ticket
  data:
    assigned_to: assignee
    status: "in_progress"
  expect:
    status: success
    field assigned_to equals assignee
    field status equals "in_progress"

test ticket_priority_levels:
  """Test all priority levels are valid."""
  setup:
    user: create User with email="test@example.com", name="Test"
  action: create Ticket
  data:
    title: "Priority Test"
    description: "Test"
    priority: "critical"
    created_by: user
  expect:
    status: success
    field priority equals "critical"

test ticket_status_progression:
  """Test ticket can progress through status workflow."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", description="Test", created_by=user, status="open"
  action: update ticket
  data:
    status: "resolved"
  expect:
    status: success
    field status equals "resolved"

test ticket_cannot_delete_with_comments:
  """Test that tickets with comments cannot be deleted."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", description="Test", created_by=user
    comment: create Comment with ticket=ticket, author=user, content="Comment"
  action: delete ticket
  expect:
    status: error
    error_message contains "has comments"

# =============================================================================
# COMMENT TESTS
# =============================================================================

test comment_requires_ticket:
  """Test that comments must belong to a ticket."""
  setup:
    user: create User with email="test@example.com", name="Test"
  action: create Comment
  data:
    author: user
    content: "Orphaned comment"
  expect:
    status: error
    error_message contains "ticket is required"

test comment_ordering:
  """Test that comments are ordered by creation time."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", description="Test", created_by=user
    comment1: create Comment with ticket=ticket, author=user, content="First"
    comment2: create Comment with ticket=ticket, author=user, content="Second"
  action: get ticket comments
  expect:
    count equals 2
    first field content equals "First"
    last field content equals "Second"

# =============================================================================
# RELATIONSHIP TESTS
# =============================================================================

test user_deletion_with_tickets:
  """Test that users with created tickets cannot be deleted (PROTECT)."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", description="Test", created_by=user
  action: delete user
  expect:
    status: error
    error_message contains "has tickets"

test user_deletion_with_assigned_tickets:
  """Test that deleting user unassigns their tickets (SET_NULL)."""
  setup:
    creator: create User with email="creator@example.com", name="Creator"
    assignee: create User with email="assignee@example.com", name="Assignee"
    ticket: create Ticket with title="Test", description="Test", created_by=creator, assigned_to=assignee
  action: delete assignee
  expect:
    status: success
    # Check ticket still exists but assigned_to is null
    ticket field assigned_to equals null

test ticket_comment_cascade:
  """Test that deleting a ticket deletes its comments (CASCADE)."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", description="Test", created_by=user
    comment: create Comment with ticket=ticket, author=user, content="Test"
  action: delete ticket
  expect:
    status: success
    # Comment should be deleted too
    comment count equals 0

# =============================================================================
# BUSINESS LOGIC TESTS
# =============================================================================

test ticket_resolved_timestamp:
  """Test that resolving a ticket sets resolved_at timestamp."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", description="Test", created_by=user
  action: update ticket
  data:
    status: "resolved"
  expect:
    status: success
    field resolved_at not_equals null

test ticket_reopen:
  """Test that resolved tickets can be reopened."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", description="Test", created_by=user, status="resolved"
  action: update ticket
  data:
    status: "open"
  expect:
    status: success
    field status equals "open"
    field resolved_at equals null  # Cleared on reopen

test high_priority_notification:
  """Test that creating high priority ticket sends notification."""
  setup:
    user: create User with email="test@example.com", name="Test"
  action: create Ticket
  data:
    title: "URGENT"
    description: "Critical issue"
    priority: "critical"
    created_by: user
  expect:
    status: success
    notification_sent: true
    notification_type equals "high_priority_ticket"
