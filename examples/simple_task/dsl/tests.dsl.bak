# Test Definitions for Simple Task Manager
# These tests define domain-specific validation beyond standard CRUD

# =============================================================================
# TASK CREATION TESTS
# =============================================================================

test task_creation_with_defaults:
  """Test task creation uses correct default values."""
  action: create Task
  data:
    title: "Test Task"
    description: "Test description"
  expect:
    status: success
    created: true
    field status equals "todo"
    field priority equals "medium"

test task_title_required:
  """Test that tasks require a title."""
  action: create Task
  data:
    description: "No title provided"
  expect:
    status: error
    error_message contains "title is required"

test task_title_max_length:
  """Test that task titles cannot exceed 200 characters."""
  action: create Task
  data:
    title: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    description: "Testing max length"
  expect:
    status: error
    error_message contains "max length"

# =============================================================================
# TASK STATUS TESTS
# =============================================================================

test task_status_values:
  """Test that only valid status values are accepted."""
  action: create Task
  data:
    title: "Status Test"
    description: "Test"
    status: "invalid_status"
  expect:
    status: error
    error_message contains "invalid choice"

test task_status_transition_todo_to_in_progress:
  """Test transitioning task from todo to in_progress."""
  setup:
    task: create Task with title="Test", description="Test", status="todo"
  action: update task
  data:
    status: "in_progress"
  expect:
    status: success
    field status equals "in_progress"

test task_status_transition_to_done:
  """Test marking task as done."""
  setup:
    task: create Task with title="Test", description="Test", status="in_progress"
  action: update task
  data:
    status: "done"
  expect:
    status: success
    field status equals "done"

# =============================================================================
# TASK PRIORITY TESTS
# =============================================================================

test task_priority_values:
  """Test all priority levels."""
  action: create Task
  data:
    title: "Priority Test"
    description: "Test"
    priority: "high"
  expect:
    status: success
    field priority equals "high"

test task_priority_low:
  """Test low priority tasks."""
  action: create Task
  data:
    title: "Low Priority"
    description: "Test"
    priority: "low"
  expect:
    status: success
    field priority equals "low"

test task_priority_invalid:
  """Test that invalid priorities are rejected."""
  action: create Task
  data:
    title: "Invalid Priority"
    description: "Test"
    priority: "super_urgent"
  expect:
    status: error
    error_message contains "invalid choice"

# =============================================================================
# TASK FILTERING TESTS
# =============================================================================

test filter_tasks_by_status:
  """Test filtering tasks by status."""
  setup:
    task1: create Task with title="Todo Task", description="Test", status="todo"
    task2: create Task with title="Done Task", description="Test", status="done"
  action: get Task
  filter:
    status: "todo"
  expect:
    count equals 1
    first field title equals "Todo Task"

test filter_tasks_by_priority:
  """Test filtering tasks by priority."""
  setup:
    task1: create Task with title="High Priority", description="Test", priority="high"
    task2: create Task with title="Low Priority", description="Test", priority="low"
  action: get Task
  filter:
    priority: "high"
  expect:
    count equals 1
    first field title equals "High Priority"

# =============================================================================
# TASK SEARCH TESTS
# =============================================================================

test search_tasks_by_title:
  """Test searching tasks by title."""
  setup:
    task1: create Task with title="Django Bug", description="Test"
    task2: create Task with title="React Feature", description="Test"
  action: get Task
  search:
    query: "Django"
  expect:
    count equals 1
    first field title contains "Django"

# =============================================================================
# TASK ORDERING TESTS
# =============================================================================

test tasks_ordered_by_priority:
  """Test that tasks can be ordered by priority."""
  setup:
    task1: create Task with title="Low", description="Test", priority="low"
    task2: create Task with title="High", description="Test", priority="high"
    task3: create Task with title="Medium", description="Test", priority="medium"
  action: get Task
  order_by: "-priority"  # High to low
  expect:
    count equals 3
    first field priority equals "high"
    last field priority equals "low"

test tasks_ordered_by_creation:
  """Test that tasks are ordered by creation date by default."""
  setup:
    task1: create Task with title="First", description="Test"
    task2: create Task with title="Second", description="Test"
  action: get Task
  expect:
    count equals 2
    # Newest first (default ordering is -created_at)
    first field title equals "Second"

# =============================================================================
# TASK UPDATE TESTS
# =============================================================================

test task_partial_update:
  """Test updating only specific fields."""
  setup:
    task: create Task with title="Original", description="Original Desc", priority="low"
  action: update task
  data:
    priority: "high"
  expect:
    status: success
    field title equals "Original"  # Unchanged
    field priority equals "high"   # Changed

test task_update_timestamps:
  """Test that updated_at changes on update."""
  setup:
    task: create Task with title="Test", description="Test"
  action: update task
  data:
    description: "Updated description"
  expect:
    status: success
    field updated_at greater_than field created_at

# =============================================================================
# TASK DELETION TESTS
# =============================================================================

test task_deletion:
  """Test deleting a task."""
  setup:
    task: create Task with title="To Delete", description="Test"
  action: delete task
  expect:
    status: success

test task_deletion_count:
  """Test that deleting reduces task count."""
  setup:
    task1: create Task with title="Task 1", description="Test"
    task2: create Task with title="Task 2", description="Test"
  action: delete task1
  expect:
    status: success
    Task count equals 1

# =============================================================================
# BUSINESS LOGIC TESTS (Future Enhancements)
# =============================================================================

test task_completion_notification:
  """Test that marking task done sends notification (if implemented)."""
  setup:
    task: create Task with title="Test", description="Test"
  action: update task
  data:
    status: "done"
  expect:
    status: success
    # notification_sent: true  # Commented - not implemented yet

test task_due_date_validation:
  """Test that due dates cannot be in the past (if implemented)."""
  action: create Task
  data:
    title: "Past Due"
    description: "Test"
    due_date: "2020-01-01"  # Past date
  expect:
    status: error
    error_message contains "due date cannot be in the past"
