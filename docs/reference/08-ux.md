# UX Semantic Layer

The UX semantic layer provides hints for intelligent UI generation, including attention signals and persona-specific customizations.

## UX Block Syntax

The `ux:` block can appear in surfaces and workspaces:

```dsl
ux:
  purpose: "Description"
  show: field1, field2
  sort: field1 desc, field2 asc
  filter: field1, field2
  search: field1, field2
  empty: "Empty state message"

  attention level:
    when: condition
    message: "Alert message"
    action: surface_name

  for persona_name:
    scope: condition | all
    # persona-specific overrides
```

## UX Properties

| Property | Description |
|----------|-------------|
| `purpose` | Human-readable description of the view's purpose |
| `show` | Fields to display (comma-separated) |
| `sort` | Default sort order |
| `filter` | Fields available for filtering |
| `search` | Fields to include in search |
| `empty` | Message when no records found |

## Attention Signals

Attention signals highlight important conditions to users:

```dsl
attention level:
  when: condition_expression
  message: "Alert message"
  action: surface_name
```

### Signal Levels

| Level | Description | Typical Use |
|-------|-------------|-------------|
| `critical` | Requires immediate action | Overdue invoices, system errors |
| `warning` | Important but not urgent | Approaching deadlines, low stock |
| `notice` | Informational alert | Status changes, new items |
| `info` | General information | Tips, suggestions |

### Condition Expressions

| Expression | Description |
|------------|-------------|
| `field == value` | Equality check |
| `field != value` | Inequality check |
| `field < value` | Less than |
| `field > value` | Greater than |
| `field <= value` | Less than or equal |
| `field >= value` | Greater than or equal |
| `condition and condition` | Logical AND |
| `condition or condition` | Logical OR |

### Built-in Values

| Value | Description |
|-------|-------------|
| `today` | Current date |
| `now` | Current datetime |
| `current_user` | Logged-in user |
| `week_start` | Start of current week |
| `month_start` | Start of current month |
| `first_day_of_month` | First day of current month |

### Attention Signal Examples

```dsl
ux:
  # Critical: Requires immediate action
  attention critical:
    when: status == "overdue" and amount > 10000
    message: "High-value invoice is critically overdue!"
    action: invoice_detail

  # Warning: Important but not urgent
  attention warning:
    when: due_date < today and status != "paid"
    message: "Invoice payment is overdue"
    action: invoice_detail

  # Notice: Status change notification
  attention notice:
    when: status == "pending_review"
    message: "Invoice ready for review"
    action: invoice_review

  # Info: General information
  attention info:
    when: created_at > week_start
    message: "New this week"
```

## Persona Variants

Customize views for different user types:

```dsl
for persona_name:
  scope: condition | all
  purpose: "Role-specific purpose"
  show: field1, field2
  hide: field1, field2
  show_aggregate: metric1, metric2
  action_primary: surface_name
  read_only: true|false
  defaults:
    field: value
  focus: region1, region2
```

### Persona Variant Properties

| Property | Description |
|----------|-------------|
| `scope` | Filter condition or `all` for full access |
| `purpose` | Role-specific description |
| `show` | Fields to display for this persona |
| `hide` | Fields to hide from this persona |
| `show_aggregate` | Aggregate metrics to display |
| `action_primary` | Default action surface |
| `read_only` | Whether persona can only view |
| `defaults` | Default field values for new records |
| `focus` | Regions to emphasize (workspaces) |

### Persona Variant Examples

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field assignee "Assignee"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"

  ux:
    purpose: "View and manage tasks"

    # Manager sees all tasks with team metrics
    for manager:
      scope: all
      purpose: "Monitor team task progress and workload"
      show: title, assignee, status, priority, due_date
      show_aggregate: total_tasks, completed_this_week, overdue_count
      action_primary: task_detail

    # Team member sees only their tasks
    for team_member:
      scope: assignee == current_user
      purpose: "View and complete my assigned tasks"
      show: title, status, priority, due_date
      hide: assignee
      action_primary: task_edit
      defaults:
        assignee: current_user

    # Observer has read-only access
    for stakeholder:
      scope: project.stakeholders contains current_user
      purpose: "Track project task progress"
      show: title, status, due_date
      hide: assignee, priority
      read_only: true

workspace project_dashboard "Project Dashboard":
  purpose: "Project overview and task tracking"

  tasks:
    source: Task
    filter: project == current_project
    display: list
    action: task_detail

  metrics:
    source: Task
    filter: project == current_project
    aggregate:
      total: count(*)
      completed: count(status == "done")
      overdue: count(due_date < today and status != "done")

  ux:
    # Project manager focuses on all regions
    for project_manager:
      scope: all
      focus: metrics, tasks
      action_primary: task_create

    # Developer focuses on task list
    for developer:
      scope: assignee == current_user
      focus: tasks
      action_primary: task_edit
```

## Complete UX Example

```dsl
surface invoice_list "Invoices":
  uses entity Invoice
  mode: list

  section main:
    field invoice_number "Invoice #"
    field customer "Customer"
    field issue_date "Issued"
    field due_date "Due Date"
    field total "Amount"
    field status "Status"

  action new "Create Invoice":
    on click -> surface invoice_create

  action view "View":
    on click -> surface invoice_detail

  ux:
    purpose: "Browse, filter, and manage customer invoices"
    show: invoice_number, customer, due_date, total, status
    sort: due_date asc
    filter: status, customer, due_date
    search: invoice_number, customer
    empty: "No invoices found. Create your first invoice to get started."

    # Critical: High-value overdue
    attention critical:
      when: status == "overdue" and total > 5000
      message: "High-value invoice requires immediate attention!"
      action: invoice_detail

    # Warning: Any overdue
    attention warning:
      when: due_date < today and status != "paid"
      message: "Invoice payment is overdue"
      action: invoice_detail

    # Notice: Due soon
    attention notice:
      when: due_date < today + 7 and due_date >= today and status == "sent"
      message: "Invoice due within 7 days"

    # Finance team has full access
    for finance:
      scope: all
      purpose: "Manage all company invoices and payments"
      show: invoice_number, customer, issue_date, due_date, total, status
      show_aggregate: total_outstanding, overdue_amount
      action_primary: invoice_detail

    # Sales sees their customer invoices
    for sales:
      scope: customer.account_manager == current_user
      purpose: "Track invoices for my accounts"
      show: invoice_number, customer, due_date, total, status
      hide: issue_date
      read_only: true
      action_primary: invoice_detail

    # Customer portal - limited view
    for customer:
      scope: customer == current_user.company
      purpose: "View my invoices and payment history"
      show: invoice_number, due_date, total, status
      hide: customer
      read_only: true
```
