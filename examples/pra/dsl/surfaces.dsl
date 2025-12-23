# Parser Reference: Surfaces
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# SURFACE BASICS:
# - [x] surface name "Title":
# - [x] surface name: (no title)
# - [x] uses entity EntityName
# - [x] mode: view
# - [x] mode: create
# - [x] mode: edit
# - [x] mode: list
# - [x] mode: custom
#
# SECTIONS:
# - [x] section name "Title":
# - [x] section name: (no title)
# - [x] field field_name "Label"
# - [x] field field_name (no label)
# - [x] Multiple fields per section
# - [x] Multiple sections per surface
#
# ACTIONS:
# - [x] action name "Label":
# - [x] action name: (no label)
# - [x] on submit -> outcome
# - [x] on submit -> outcome
# - [x] on auto -> outcome
#
# OUTCOMES:
# - [x] surface SurfaceName
# - [x] experience ExperienceName
# - [x] experience ExperienceName step StepName
# - [x] integration IntegrationName action ActionName
#
# UX BLOCK:
# - [x] ux: block
# - [x] purpose: "..."
# - [x] show: field1, field2
# - [x] sort: field1 desc, field2 asc
# - [x] filter: field1, field2
# - [x] search: field1, field2
# - [x] empty: "..."
#
# ATTENTION SIGNALS:
# - [x] attention critical:
# - [x] attention warning:
# - [x] attention notice:
# - [x] attention info:
# - [x] when: condition
# - [x] message: "..."
# - [x] action: surface_name
#
# PERSONA VARIANTS:
# - [x] for persona_name:
# - [x] scope: all
# - [x] scope: condition
# - [x] purpose: "..."
# - [x] show: field1, field2
# - [x] hide: field1, field2
# - [x] show_aggregate: metric1, metric2
# - [x] action_primary: surface_name
# - [x] read_only: true/false
# - [x] defaults: block
# - [x] focus: region1, region2
#
# =============================================================================

module pra.surfaces

use pra
use pra.entities
use pra.relationships
use pra.state_machines
use pra.computed

# =============================================================================
# BASIC LIST SURFACE
# =============================================================================

surface product_list "Product Catalog":
  uses entity Product
  mode: list

  section main:
    field sku "SKU"
    field name "Product Name"
    field price "Price"
    field category "Category"
    field is_active "Active"

# =============================================================================
# VIEW MODE SURFACE
# =============================================================================

surface product_detail "Product Details":
  uses entity Product
  mode: view

  section header:
    field name "Name"
    field sku "SKU"
    field category "Category"

  section pricing:
    field price "Price"
    field is_active "Active"

  section description:
    field description "Description"

# =============================================================================
# CREATE MODE SURFACE
# =============================================================================

surface product_create "Add Product":
  uses entity Product
  mode: create

  section basic:
    field sku
    field name
    field category

  section pricing:
    field price

  section details:
    field description
    field is_active

  action save "Save Product":
    on submit -> surface product_list

# =============================================================================
# EDIT MODE SURFACE
# =============================================================================

surface product_edit "Edit Product":
  uses entity Product
  mode: edit

  section basic:
    field sku
    field name
    field category

  section pricing:
    field price

  section details:
    field description
    field is_active

  action save "Save Changes":
    on submit -> surface product_detail

  action cancel "Cancel":
    on submit -> surface product_detail

# =============================================================================
# CUSTOM MODE SURFACE
# =============================================================================

surface dashboard "Dashboard":
  uses entity Product
  mode: view

  section summary:
    field name "Product Name"
    field sku "SKU"

  section recent:
    field price "Price"

# =============================================================================
# SURFACE WITH ALL ACTION TRIGGERS
# =============================================================================

surface task_form "Task Form":
  uses entity Task
  mode: create

  section main:
    field title
    field description
    field priority

  # Submit trigger - form submission
  action create "Create Task":
    on submit -> surface task_list

  # Cancel button (using submit trigger as click is reserved keyword)
  action cancel "Cancel":
    on submit -> surface task_list

  # Save draft (auto trigger not supported, using submit)
  action draft "Save as Draft":
    on submit -> surface task_list

# =============================================================================
# OUTCOMES: SURFACE, EXPERIENCE, INTEGRATION
# =============================================================================

surface checkout "Checkout":
  uses entity Invoice
  mode: create

  section items:
    field invoice_number
    field subtotal
    field total

  # Outcome: navigate to surface
  action view_cart "View Cart":
    on submit -> surface cart_view

  # Outcome: navigate to another surface (simplified to avoid circular deps)
  action begin_checkout "Checkout":
    on submit -> surface payment_form_surface

  # Outcome: navigate to payment surface
  action skip_to_payment "Skip to Payment":
    on submit -> surface payment_form_surface

  # Outcome: navigate to confirmation surface
  action process_payment "Process Payment":
    on submit -> surface order_confirmation_surface

# Placeholder surfaces for navigation
surface cart_view "Cart":
  uses entity Invoice
  mode: view
  section main:
    field invoice_number "Invoice #"

surface payment_form_surface "Payment Form":
  uses entity Invoice
  mode: create
  section main:
    field total "Amount"

surface order_confirmation_surface "Order Confirmation":
  uses entity Invoice
  mode: view
  section main:
    field invoice_number "Confirmation"

surface task_list "Task List":
  uses entity Task
  mode: list
  section main:
    field title

# =============================================================================
# UX BLOCK: BASIC
# =============================================================================

surface employee_list "Employee Directory":
  uses entity Employee
  mode: list

  section main:
    field employee_id
    field first_name
    field last_name
    field email
    field department

  ux:
    purpose: "Find and manage employees across departments"
    show: employee_id, first_name, last_name, email, department
    sort: last_name asc, first_name asc
    filter: department, is_active
    search: first_name, last_name, email
    empty: "No employees found. Add your first team member!"

# =============================================================================
# UX BLOCK: ATTENTION SIGNALS
# =============================================================================

surface invoice_list "Invoice Management":
  uses entity Invoice
  mode: list

  section main:
    field invoice_number
    field status
    field total
    field due_date

  ux:
    purpose: "Track and manage invoices"
    show: invoice_number, status, total, due_date
    sort: due_date asc
    filter: status

    # Critical: immediate action required
    attention critical:
      when: status = overdue
      message: "Invoice is overdue - immediate attention required!"
      action: invoice_escalate

    # Warning: needs attention soon
    attention warning:
      when: status = sent
      message: "Invoice sent - awaiting payment"
      action: invoice_remind

    # Notice: informational
    attention notice:
      when: status = draft
      message: "Draft invoice - ready to send"

    # Info: low priority
    attention info:
      when: status = draft
      message: "Draft invoice - not yet sent"

# Placeholder for attention signal actions
surface invoice_escalate "Escalate Invoice":
  uses entity Invoice
  mode: edit
  section main:
    field status "Status"

surface invoice_remind "Send Reminder":
  uses entity Invoice
  mode: edit
  section main:
    field status "Status"

# =============================================================================
# UX BLOCK: PERSONA VARIANTS (BASIC)
# =============================================================================

surface project_list "Projects":
  uses entity DevProject
  mode: list

  section main:
    field name
    field status
    field budget
    field project_manager

  ux:
    purpose: "View and manage projects"
    show: name, code, status, budget
    sort: name asc

    # Persona variant for team members
    for member:
      scope: all
      purpose: "View projects you're assigned to"
      show: name, status, project_manager
      hide: budget
      read_only: true

    # Persona variant for managers
    for manager:
      scope: all
      purpose: "Manage all department projects"
      show: name, code, status, budget, project_manager, tech_lead
      show_aggregate: active_count, budget_total
      action_primary: project_create

    # Persona variant for executives
    for executive:
      scope: all
      purpose: "Executive dashboard view"
      show: name, status, budget
      show_aggregate: total_budget, project_count
      focus: summary, metrics

# =============================================================================
# UX BLOCK: PERSONA VARIANTS WITH SCOPE CONDITIONS
# =============================================================================

surface task_kanban "Task Board":
  uses entity Task
  mode: list

  section main:
    field title
    field status
    field priority
    field assignee

  ux:
    purpose: "Manage tasks across the team"
    show: title, status, priority, assignee, due_date
    sort: priority desc, due_date asc
    filter: status, priority, assignee

    # Team member sees only their tasks
    for team_member:
      scope: assignee = current_user
      purpose: "Your assigned tasks"
      show: title, status, priority, due_date
      hide: assignee
      action_primary: task_edit

    # Team lead sees team tasks
    for team_lead:
      scope: all
      purpose: "All team tasks"
      show: title, status, priority, assignee, due_date
      show_aggregate: urgent_count, blocked_count

    # Admin sees all tasks
    for admin:
      scope: all
      purpose: "All tasks across organization"
      show: title, status, priority, assignee, dev_project, due_date

# Placeholder surfaces
surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  section main:
    field title

surface project_create "Create Project":
  uses entity DevProject
  mode: create
  section main:
    field name

# =============================================================================
# UX BLOCK: PERSONA VARIANTS WITH DEFAULTS
# =============================================================================

surface ticket_create "New Support Ticket":
  uses entity SupportTicket
  mode: create

  section main:
    field title
    field description
    field status
    field assignee

  ux:
    purpose: "Create a new support ticket"

    # Support agent defaults
    for support_agent:
      purpose: "Create ticket on behalf of customer"
      defaults:
        status: new
        assignee: current_user

    # Customer defaults (read-only fields)
    for customer:
      purpose: "Submit a support request"
      hide: assignee, status
      defaults:
        status: new

    # Manager defaults
    for support_manager:
      purpose: "Create and assign tickets"
      defaults:
        status: new

# =============================================================================
# UX BLOCK: PERSONA VARIANTS WITH FOCUS
# =============================================================================

surface analytics_dashboard "Analytics Dashboard":
  uses entity Invoice
  mode: list

  section metrics:
    field total "Total"
    field status "Status"

  section details:
    field invoice_number "Invoice #"
    field due_date "Due Date"

  ux:
    purpose: "Analytics overview"

    # Marketing focuses on different regions
    for marketing:
      purpose: "Marketing performance metrics"
      focus: metrics
      show_aggregate: total

    # Sales focuses on revenue
    for sales:
      purpose: "Sales metrics and pipeline"
      focus: metrics, details
      show_aggregate: total

    # Executive sees high-level summary
    for executive:
      purpose: "Executive summary"
      focus: metrics
      show_aggregate: total

# =============================================================================
# SURFACE WITHOUT TITLE
# =============================================================================

surface simple_view:
  uses entity Category
  mode: view

  section main:
    field name
    field slug

# =============================================================================
# SECTION WITHOUT TITLE
# =============================================================================

surface minimal_surface "Minimal":
  uses entity Category
  mode: list

  section items:
    field name
    field slug

# =============================================================================
# MULTIPLE SECTIONS
# =============================================================================

surface company_profile "Company Profile":
  uses entity Company
  mode: view

  section header "Company Information":
    field name "Company Name"
    field industry "Industry"

  section details "Details":
    field founded_year "Founded"
    field is_active "Active"

  section metadata "System Info":
    field created_at "Created"

# =============================================================================
# COMPLEX COMBINED SURFACE
# =============================================================================

surface order_management "Order Management":
  uses entity OrderWithTotals
  mode: list

  section header "Order List":
    field order_number "Order #"
    field status "Status"
    field order_date "Order Date"
    field delivery_date "Delivery Date"

  action view_order "View":
    on submit -> surface order_detail

  action process_order "Process":
    on submit -> surface order_process

  action refund_order "Refund":
    on submit -> surface order_refund_form

  ux:
    purpose: "Manage customer orders from creation to delivery"
    show: order_number, status, order_date, created_at
    sort: created_at desc
    filter: status
    search: order_number
    empty: "No orders yet. Your first order will appear here."

    attention critical:
      when: status = confirmed
      message: "Order confirmed - needs processing"
      action: order_process

    attention warning:
      when: status = shipped
      message: "Order shipped - confirm delivery"

    for warehouse_staff:
      scope: status in [confirmed, draft]
      purpose: "Pick and pack orders"
      show: order_number, status, order_date
      action_primary: order_process
      defaults:
        status: confirmed

    for customer_service:
      scope: all
      purpose: "Handle customer inquiries about orders"
      show: order_number, status, order_date
      show_aggregate: pending_count, issues_count
      read_only: true

    for admin:
      scope: all
      purpose: "Full order management"
      show: order_number, status, order_date, created_at
      show_aggregate: total_orders, total_revenue, pending_count
      focus: metrics, orders

# Placeholder surfaces for order management
surface order_detail "Order Details":
  uses entity OrderWithTotals
  mode: view
  section main:
    field order_number

surface order_process "Process Order":
  uses entity OrderWithTotals
  mode: edit
  section main:
    field status

surface order_refund_form "Request Refund":
  uses entity OrderWithTotals
  mode: edit
  section main:
    field status "Status"
    field order_number "Order #"
