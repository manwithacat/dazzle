# Surfaces

Surfaces define UI screens and forms for interacting with entities.

## Basic Syntax

```dsl
surface surface_name "Display Title":
  uses entity EntityName
  mode: view|create|edit|list|custom

  section section_name "Section Title":
    field field_name "Label"

  action action_name "Label":
    on trigger -> outcome
```

## Surface Modes

| Mode | Description |
|------|-------------|
| `view` | Read-only display of single record |
| `create` | Form for creating new record |
| `edit` | Form for editing existing record |
| `list` | Table/list of multiple records |
| `custom` | Fully custom layout |

## Sections

Group related fields into sections:

```dsl
surface customer_detail "Customer Details":
  uses entity Customer
  mode: view

  section info "Basic Information":
    field name "Full Name"
    field email "Email Address"
    field phone "Phone"

  section billing "Billing Details":
    field billing_address "Address"
    field payment_method "Payment Method"
```

## Actions

Define interactive actions with triggers and outcomes:

```dsl
surface task_form "Create Task":
  uses entity Task
  mode: create

  section main:
    field title "Title"
    field description "Description"
    field due_date "Due Date"

  action save "Save Task":
    on submit -> surface task_list

  action cancel "Cancel":
    on click -> surface task_list
```

### Triggers

| Trigger | Description |
|---------|-------------|
| `submit` | Form submission |
| `click` | Button click |
| `auto` | Automatic (on load) |

### Outcomes

Navigate to another surface, experience, or trigger integration:

```dsl
# Navigate to surface
on submit -> surface task_list

# Navigate to experience at specific step
on submit -> experience onboarding step welcome

# Trigger integration action
on submit -> integration payment action process_payment
```

## UX Semantic Layer

Add UX hints for smarter UI generation:

```dsl
surface invoice_list "Invoices":
  uses entity Invoice
  mode: list

  section main:
    field invoice_number "Number"
    field customer "Customer"
    field total "Total"
    field status "Status"
    field due_date "Due Date"

  ux:
    purpose: "View and manage customer invoices"
    show: invoice_number, customer, total, status, due_date
    sort: due_date asc
    filter: status, customer
    search: invoice_number, customer
    empty: "No invoices found. Create your first invoice to get started."

    attention critical:
      when: status == "overdue" and total > 1000
      message: "High-value invoice is overdue!"
      action: invoice_detail

    attention warning:
      when: due_date < today and status != "paid"
      message: "Invoice payment is overdue"
```

## Complete Example

```dsl
# List view
surface order_list "Orders":
  uses entity Order
  mode: list

  section main:
    field order_number "Order #"
    field customer "Customer"
    field order_date "Date"
    field status "Status"
    field subtotal "Total"

  action new "New Order":
    on click -> surface order_create

  action view "View":
    on click -> surface order_detail

  ux:
    purpose: "Browse and manage customer orders"
    sort: order_date desc
    filter: status, customer
    search: order_number, customer

# Create form
surface order_create "Create Order":
  uses entity Order
  mode: create

  section customer "Customer Info":
    field customer "Customer"
    field order_date "Order Date"

  section items "Order Items":
    field items "Line Items"

  section options "Options":
    field is_gift "Gift Order?"
    field notes "Notes"

  action save "Create Order":
    on submit -> surface order_detail

  action cancel "Cancel":
    on click -> surface order_list

# Detail view
surface order_detail "Order Details":
  uses entity Order
  mode: view

  section header "Order Information":
    field order_number "Order Number"
    field customer "Customer"
    field status "Status"
    field order_date "Order Date"

  section financial "Financial":
    field subtotal "Subtotal"
    field tax_rate "Tax Rate"
    field items "Line Items"

  section dates "Timestamps":
    field created_at "Created"
    field updated_at "Last Updated"

  action edit "Edit":
    on click -> surface order_edit

  action back "Back to List":
    on click -> surface order_list

# Edit form
surface order_edit "Edit Order":
  uses entity Order
  mode: edit

  section main:
    field status "Status"
    field notes "Notes"
    field is_gift "Gift Order?"

  action save "Save Changes":
    on submit -> surface order_detail

  action cancel "Cancel":
    on click -> surface order_detail
```

## Persona Variants

Customize surfaces per persona:

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field assignee "Assignee"
    field status "Status"
    field due_date "Due"

  ux:
    for manager:
      scope: all
      purpose: "Monitor team task progress"
      show: title, assignee, status, due_date
      show_aggregate: total_tasks, overdue_count
      action_primary: task_detail

    for team_member:
      scope: assignee == current_user
      purpose: "View and complete my assigned tasks"
      show: title, status, due_date
      hide: assignee
      action_primary: task_edit
      read_only: false
```
